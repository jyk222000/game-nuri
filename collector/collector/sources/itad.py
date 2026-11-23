"""ITAD → raw.price

수집 대상은 `analysis/game_list/games_1000.csv`의 `itad_id` (Steam appid로 미리 조회해 둔 값).
응답은 가공하지 않고 봉투(payload)에 그대로 담는다.

| kind | 호출 | 봉투 단위 | 주기 |
|---|---|---|---|
| price | POST /games/prices/v3 (country=KR) | 게임 1건 `{id, historyLow, deals[]}` | 6시간 |
| price_history | GET /games/history/v2 | 게임 1건 `{id, history[]}` | 처음 1번 + 주 1번 |

- 키는 쿼리 파라미터(`key`)로 가므로 URL·예외 문구에 절대 넣지 않는다.
- 한도는 5분당 1,000건. 현재가는 100게임씩 한 번에, 이력은 게임당 1회(1,000게임 약 8분).
- 이력 가격의 통화는 판매처에 따라 KRW(한국에서 파는 곳)나 USD로 섞여 온다. 환산은 정제기가 한다.
"""

from __future__ import annotations

import csv
import json
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import requests
from gamenuri_common.config import get_settings
from gamenuri_common.logging import get_logger
from gamenuri_common.messages import RawEnvelope

log = get_logger("collector.itad")

API_URL = "https://api.isthereanydeal.com"
PRICES_PATH = "/games/prices/v3"
HISTORY_PATH = "/games/history/v2"
HISTORY_FULL_SINCE = "2000-01-01T00:00:00Z"  # since가 없으면 최근 약 3개월만 온다
MAX_MESSAGE_BYTES = 800_000  # Kafka 메시지 기본 한도(1MB)보다 작게
COUNTRY = "KR"
USER_AGENT = "game-nuri-collector/0.1"

MIN_INTERVAL_SEC = 0.5  # 5분 1,000건 한도에 비해 충분히 느리게
BATCH_SIZE = 100  # 한 번에 보내는 게임 수
MAX_RETRIES = 3  # 429·5xx 재시도 횟수 (지수 백오프)
DEFAULT_GAMES_FILE = (
    Path(__file__).resolve().parents[3] / "analysis" / "game_list" / "games_1000.csv"
)


class ItadError(RuntimeError):
    pass


@dataclass(frozen=True)
class Target:
    itad_id: str
    steam_appid: int | None  # 정제기가 게임 ID를 찾을 때 쓰는 힌트


def load_targets(path: Path = DEFAULT_GAMES_FILE, limit: int | None = None) -> list[Target]:
    """games_1000.csv에서 itad_id가 있는 게임을 rank 순서대로 읽는다 (중복 제거)."""
    out: list[Target] = []
    seen: set[str] = set()
    skipped = 0
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            itad_id = (row.get("itad_id") or "").strip()
            if not itad_id:
                skipped += 1
                continue
            if itad_id in seen:
                continue
            seen.add(itad_id)
            appid = (row.get("steam_appid") or "").strip()
            out.append(Target(itad_id, int(appid) if appid.isdigit() else None))
    if skipped:
        log.warning("itad_id가 없어 건너뛴 게임 %d건", skipped)
    return out[:limit] if limit else out


class ItadClient:
    """ITAD를 호출한다. 호출 간격과 재시도를 여기서 강제하고, 오류에 키를 싣지 않는다."""

    def __init__(
        self,
        key: str,
        session: requests.Session | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not key:
            raise ItadError("ITAD_KEY 가 비어 있다 (.env 확인)")
        self._key = key
        self._s = session or requests.Session()
        self._sleep = sleep
        self._clock = clock
        self._last_call = float("-inf")

    @classmethod
    def from_settings(cls) -> ItadClient:
        return cls(get_settings().itad_key)

    def _throttle(self) -> None:
        wait = MIN_INTERVAL_SEC - (self._clock() - self._last_call)
        if wait > 0:
            self._sleep(wait)
        self._last_call = self._clock()

    def post(self, path: str, params: dict[str, Any], body: Any) -> Any:
        """POST. 응답 JSON 원본을 그대로 돌려준다. 오류 문구에는 경로와 상태 코드만 쓴다."""
        return self._request("POST", path, params, body)

    def get(self, path: str, params: dict[str, Any]) -> Any:
        """GET. 응답 JSON 원본을 그대로 돌려준다 (가격 이력 `games/history/v2`)."""
        return self._request("GET", path, params, None)

    def _request(self, method: str, path: str, params: dict[str, Any], body: Any) -> Any:
        for attempt in range(MAX_RETRIES + 1):
            self._throttle()
            send = self._s.post if method == "POST" else self._s.get
            kwargs: dict[str, Any] = {} if body is None else {"json": body}
            r = send(
                API_URL + path,
                params={"key": self._key, **params},
                headers={"User-Agent": USER_AGENT},
                timeout=30,
                **kwargs,
            )
            if r.status_code == 429 or r.status_code >= 500:
                if attempt == MAX_RETRIES:
                    break
                delay = float(r.headers.get("Retry-After", 2 ** (attempt + 1)))
                log.warning(
                    "ITAD %s HTTP %s, %ss 후 재시도 (%s/%s)",
                    path,
                    r.status_code,
                    delay,
                    attempt + 1,
                    MAX_RETRIES,
                )
                self._sleep(delay)
                continue
            if not r.ok:
                raise ItadError(f"ITAD {path} HTTP {r.status_code}")
            return r.json()
        raise ItadError(f"ITAD {path} 재시도 초과")


def collect(
    targets: list[Target], client: ItadClient | None = None
) -> Iterator[tuple[str, RawEnvelope]]:
    """게임 목록 → (Kafka 키 = itad_id, 봉투). 게임 1건이 봉투 1개다."""
    client = client or ItadClient.from_settings()
    appid_of = {t.itad_id: t.steam_appid for t in targets}

    got = 0
    for i in range(0, len(targets), BATCH_SIZE):
        chunk = targets[i : i + BATCH_SIZE]
        ids = [t.itad_id for t in chunk]
        rows = client.post(PRICES_PATH, {"country": COUNTRY}, ids)
        for row in rows:
            got += 1
            params: dict[str, Any] = {"country": COUNTRY}
            if appid_of.get(row["id"]) is not None:
                params["steam_appid"] = appid_of[row["id"]]
            yield (
                row["id"],
                RawEnvelope(
                    source="itad",
                    kind="price",
                    request={"url": API_URL + PRICES_PATH, "params": params},
                    payload=row,
                ),
            )
        returned = {r["id"] for r in rows}
        missing = [x for x in ids if x not in returned]
        if missing:
            log.warning("ITAD가 돌려주지 않은 게임 %d건: %s", len(missing), missing[:5])
    log.info("ITAD 수집 완료: %d/%d건", got, len(targets))


# ---------------------------------------------------------------- 가격 이력 (price_history)
def since_from_days(days: int | None, now: datetime | None = None) -> str:
    """`--since-days N` → ITAD `since` 값 (UTC). 없으면 전체 이력(2000-01-01)."""
    if days is None:
        return HISTORY_FULL_SINCE
    now = now or datetime.now(UTC)
    return (now - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")


def split_history(
    items: list[dict[str, Any]], max_bytes: int = MAX_MESSAGE_BYTES
) -> Iterator[list[dict[str, Any]]]:
    """이력 항목을 JSON 크기가 max_bytes를 넘지 않게 나눈다 (Kafka 메시지 한도 대비)."""
    chunk: list[dict[str, Any]] = []
    size = 0
    for it in items:
        n = len(json.dumps(it, ensure_ascii=False).encode()) + 1
        if chunk and size + n > max_bytes:
            yield chunk
            chunk, size = [], 0
        chunk.append(it)
        size += n
    if chunk:
        yield chunk


def collect_history(
    targets: list[Target],
    client: ItadClient | None = None,
    since: str = HISTORY_FULL_SINCE,
    max_bytes: int = MAX_MESSAGE_BYTES,
) -> Iterator[tuple[str, RawEnvelope]]:
    """게임마다 `games/history/v2`를 받아 (키 = itad_id, 봉투)를 낸다 (계약 raw.price_history.json).

    payload = {"id": itad_id, "history": 응답 항목 그대로}. 메시지가 max_bytes를 넘으면 같은
    모양으로 여러 개로 나눈다. 한 게임이 실패해도 계속한다. 같은 이력을 다시 받아도
    정제·Backend가 합치므로 겹쳐도 된다 (주 1회 수집은 `since`를 며칠 앞당겨 겹치게 받는다).
    """
    client = client or ItadClient.from_settings()
    sent = empty = failed = 0
    for t in targets:
        params = {"id": t.itad_id, "country": COUNTRY, "since": since}
        try:
            items = client.get(HISTORY_PATH, params)
        except ItadError as e:
            failed += 1
            log.warning("가격 이력 %s 실패: %s", t.itad_id, e)
            continue
        if not isinstance(items, list) or not items:
            empty += 1
            continue
        req: dict[str, Any] = {"id": t.itad_id, "country": COUNTRY, "since": since}
        if t.steam_appid is not None:
            req["appid"] = str(t.steam_appid)
        for chunk in split_history(items, max_bytes):
            sent += 1
            yield (
                t.itad_id,
                RawEnvelope(
                    source="itad",
                    kind="price_history",
                    request={"url": API_URL + HISTORY_PATH, "params": req},
                    payload={"id": t.itad_id, "history": chunk},
                ),
            )
    log.info("ITAD 가격 이력 수집 완료: 메시지 %d, 이력 없음 %d, 실패 %d", sent, empty, failed)
