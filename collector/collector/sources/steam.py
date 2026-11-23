"""Steam: 사양(appdetails)·동접자·리뷰 → raw.steam  (키 불필요)

수집 대상은 `analysis/game_list/games_1000.csv`의 `steam_appid`.
응답은 가공하지 않고 봉투(payload)에 그대로 담는다.

| kind | 호출 | 봉투 단위 | 주기 |
|---|---|---|---|
| app_details | store.steampowered.com/api/appdetails (cc=kr, l=koreana) | 게임 1건 | 매일 |
| player_count | ISteamUserStats/GetNumberOfCurrentPlayers | 게임 1건 | 1시간 |
| review | IUserReviewsService/GetAppReviews (한국어, 최신순, 증분) | 리뷰 1건 | 매일 |

모든 봉투의 `request.params.appid`에 appid를 넣는다 (정제기가 게임을 찾는 힌트).
보유 게임(owned_games)은 사용자 요청에 따라 도는 흐름이라 아직 만들지 않았다.
"""

from __future__ import annotations

import csv
import json
import math
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import requests
from gamenuri_common.logging import get_logger
from gamenuri_common.messages import RawEnvelope

log = get_logger("collector.steam")

USER_AGENT = "game-nuri-collector/0.1"
APPDETAILS_URL = "https://store.steampowered.com/api/appdetails"
PLAYERS_URL = "https://api.steampowered.com/ISteamUserStats/GetNumberOfCurrentPlayers/v1/"
REVIEWS_URL = "https://api.steampowered.com/IUserReviewsService/GetAppReviews/v1/"

# 호출 종류별 (최소 간격 초, 429·5xx 때 첫 대기 초). appdetails는 5분 200회 정도가 한도라 느리게.
LIMITS: dict[str, tuple[float, float]] = {
    "appdetails": (1.6, 30.0),
    "players": (0.3, 2.0),
    "reviews": (0.5, 5.0),
}
MAX_RETRIES = 3
REVIEWS_PER_PAGE = 100
DEFAULT_MAX_REVIEWS = 500  # 게임당 한 번에 받는 새 리뷰 상한 (⑤ 요약에 필요한 양은 팀 결정 전)
DEFAULT_GAMES_FILE = (
    Path(__file__).resolve().parents[3] / "analysis" / "game_list" / "games_1000.csv"
)
DEFAULT_STATE_FILE = Path(__file__).resolve().parents[2] / "state" / "steam_reviews.json"


class SteamError(RuntimeError):
    pass


def load_appids(path: Path = DEFAULT_GAMES_FILE, limit: int | None = None) -> list[int]:
    """games_1000.csv의 steam_appid를 rank 순으로 읽는다 (없는 게임은 건너뛰고, 중복 제거)."""
    out: list[int] = []
    seen: set[int] = set()
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            s = (row.get("steam_appid") or "").strip()
            if s.isdigit() and int(s) not in seen:
                seen.add(int(s))
                out.append(int(s))
    return out[:limit] if limit else out


class SteamClient:
    """Steam GET 호출. 종류별 호출 간격과 재시도를 여기서 강제한다."""

    def __init__(
        self,
        session: requests.Session | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._s = session or requests.Session()
        self._sleep = sleep
        self._clock = clock
        self._last: dict[str, float] = {}

    def _throttle(self, kind: str) -> None:
        wait = LIMITS[kind][0] - (self._clock() - self._last.get(kind, float("-inf")))
        if wait > 0:
            self._sleep(wait)
        self._last[kind] = self._clock()

    def get(self, kind: str, url: str, params: dict[str, Any]) -> Any:
        """GET → JSON 원본. 오류 문구에는 주소와 상태 코드만 쓴다."""
        base = url.split("?")[0]
        backoff = LIMITS[kind][1]
        for attempt in range(MAX_RETRIES + 1):
            self._throttle(kind)
            r = self._s.get(url, params=params, headers={"User-Agent": USER_AGENT}, timeout=30)
            if r.status_code == 429 or r.status_code >= 500:
                if attempt == MAX_RETRIES:
                    break
                delay = float(r.headers.get("Retry-After", backoff * 2**attempt))
                log.warning(
                    "Steam %s HTTP %s, %ss 후 재시도 (%s/%s)",
                    kind,
                    r.status_code,
                    delay,
                    attempt + 1,
                    MAX_RETRIES,
                )
                self._sleep(delay)
                continue
            if not r.ok:
                raise SteamError(f"Steam {base} HTTP {r.status_code}")
            return r.json()
        raise SteamError(f"Steam {base} 재시도 초과")


# ---------------------------------------------------------------- 사양 (app_details)
def collect_app_details(
    appids: list[int], client: SteamClient | None = None
) -> Iterator[tuple[str, RawEnvelope]]:
    """appdetails 응답({"<appid>": {"success", "data"}})을 그대로 담는다. 실패해도 계속한다."""
    client = client or SteamClient()
    ok = failed = 0
    for appid in appids:
        params = {"appids": appid, "cc": "kr", "l": "koreana"}
        try:
            body = client.get("appdetails", APPDETAILS_URL, params)
        except SteamError as e:
            failed += 1
            log.warning("appdetails %s 실패: %s", appid, e)
            continue
        if not (body.get(str(appid)) or {}).get("success"):
            failed += 1
            log.warning("appdetails %s: success=false (판매 중단·지역 제한)", appid)
            continue
        ok += 1
        yield (
            str(appid),
            RawEnvelope(
                source="steam",
                kind="app_details",
                request={"url": APPDETAILS_URL, "params": {**params, "appid": appid}},
                payload=body,
            ),
        )
    log.info("Steam 사양 수집 완료: 성공 %d, 실패 %d", ok, failed)


# ---------------------------------------------------------------- 동접자 (player_count)
def collect_player_counts(
    appids: list[int], client: SteamClient | None = None
) -> Iterator[tuple[str, RawEnvelope]]:
    client = client or SteamClient()
    ok = failed = 0
    for appid in appids:
        try:
            body = client.get("players", PLAYERS_URL, {"appid": appid})
        except SteamError as e:
            failed += 1
            log.warning("동접자 %s 실패: %s", appid, e)
            continue
        ok += 1
        yield (
            str(appid),
            RawEnvelope(
                source="steam",
                kind="player_count",
                request={"url": PLAYERS_URL, "params": {"appid": appid}},
                payload=body,
            ),
        )
    log.info("Steam 동접자 수집 완료: 성공 %d, 실패 %d", ok, failed)


# ---------------------------------------------------------------- 리뷰 (review, 증분)
class ReviewState:
    """게임별로 어디까지 받았는지 (가장 새 리뷰의 시각과, 그 시각에 있던 리뷰 id들).

    `update()`는 메모리만 바꾼다. 파일 저장(`save()`)은 Kafka 전송 성공을 확인한 뒤에 호출한다.
    전송이 실패했는데 "받았다"고 기록하면 그 리뷰들이 영영 빠진다.
    """

    def __init__(self, path: Path = DEFAULT_STATE_FILE) -> None:
        self.path = path
        self.data: dict[str, dict[str, Any]] = {}
        if path.exists():
            self.data = json.loads(path.read_text(encoding="utf-8"))

    def get(self, appid: int) -> tuple[int, set[str]]:
        s = self.data.get(str(appid)) or {}
        return int(s.get("last_created", 0)), set(s.get("ids_at_last", []))

    def update(self, appid: int, new_reviews: list[dict[str, Any]]) -> None:
        if not new_reviews:
            return
        last, ids = self.get(appid)
        newest = max(int(r["timestamp_created"]) for r in new_reviews)
        at_newest = {
            str(r["recommendationid"]) for r in new_reviews if int(r["timestamp_created"]) == newest
        }
        if newest == last:
            at_newest |= ids
        if newest >= last:
            self.data[str(appid)] = {"last_created": newest, "ids_at_last": sorted(at_newest)}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path)


def _is_new(r: dict[str, Any], last: int, ids_at_last: set[str]) -> bool:
    created = int(r["timestamp_created"])
    return created > last or (created == last and str(r["recommendationid"]) not in ids_at_last)


def collect_reviews(
    appids: list[int],
    client: SteamClient | None = None,
    state: ReviewState | None = None,
    max_reviews: int = DEFAULT_MAX_REVIEWS,
) -> Iterator[tuple[str, RawEnvelope]]:
    """한국어 리뷰를 최신순으로 받다가 이미 받은 리뷰를 만나면 멈춘다. 리뷰 1건 = 봉투 1개.

    payload = 리뷰 객체 그대로 + steam_appid. (Mongo `reviews`·ES에 한 건씩 문서가 되게 하려고
    페이지 단위가 아니라 한 건씩 보낸다.) 이미 받은 리뷰는 보내지 않는다.
    페이지 단위 정보(`query_summary`, `total_matching`, `cursor`)는 담지 않는다.
    최초 실행은 게임당 최신 max_reviews건까지만 받는다.
    """
    client = client or SteamClient()
    state = state or ReviewState()
    total = failed = 0
    for appid in appids:
        last, ids_at_last = state.get(appid)
        collected: list[dict[str, Any]] = []
        cursor = "*"
        try:
            for _ in range(math.ceil(max_reviews / REVIEWS_PER_PAGE) + 2):  # 안전장치
                query = {
                    "appid": appid,
                    "languages": ["koreana"],
                    "filter": 1,
                    "purchase_type": 1,
                    "review_type": 0,
                    "num_per_page": REVIEWS_PER_PAGE,
                    "cursor": cursor,
                }
                body = client.get("reviews", REVIEWS_URL, {"input_json": json.dumps(query)})
                resp = body.get("response", body)
                reviews = resp.get("reviews") or []
                new = [r for r in reviews if _is_new(r, last, ids_at_last)]
                new = new[: max_reviews - len(collected)]
                collected += new
                for r in new:  # 리뷰 1건 = 봉투 1개. 키는 steam_appid (게임별 순서 유지)
                    yield (
                        str(appid),
                        RawEnvelope(
                            source="steam",
                            kind="review",
                            request={
                                "url": REVIEWS_URL,
                                "params": {"appid": appid, "input": query},
                            },
                            payload={"steam_appid": appid, **r},
                        ),
                    )
                nxt = resp.get("cursor")
                # 끝: 0건 페이지, 아는 리뷰를 만남, 상한 도달, cursor 없음/반복
                if (
                    not reviews
                    or len(new) < len(reviews)
                    or len(collected) >= max_reviews
                    or not nxt
                    or nxt == cursor
                ):
                    break
                cursor = nxt
        except SteamError as e:
            failed += 1
            log.warning("리뷰 %s 실패 (여기까지 %d건은 보냄): %s", appid, len(collected), e)
        state.update(appid, collected)
        total += len(collected)
    log.info("Steam 리뷰 수집 완료: 새 리뷰 %d건, 실패 게임 %d", total, failed)
