"""IGDB: Twitch 토큰 → /v4/games, /v4/game_time_to_beats → raw.igdb

수집 대상은 `analysis/game_list/games_1000.csv`의 `game_id`(= IGDB ID) 1,000건이다.
응답은 가공하지 않고 봉투(payload)에 그대로 담는다. 필드 확장(`genres.name` 등)만 요청에서 한다.

- 게임 정보: 게임 1건 = 봉투 1개 (kind=game_info, 키=igdb_id)
- 클리어 시간: 행 1건 = 봉투 1개 (kind=time_to_beat, 키=game_id, payload에 game_id 포함)
"""

from __future__ import annotations

import csv
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import requests
from gamenuri_common.config import get_settings
from gamenuri_common.logging import get_logger
from gamenuri_common.messages import RawEnvelope

log = get_logger("collector.igdb")

TOKEN_URL = "https://id.twitch.tv/oauth2/token"
API_URL = "https://api.igdb.com/v4"
USER_AGENT = "game-nuri-collector/0.1"

MIN_INTERVAL_SEC = 0.26  # 초당 4회 한도 (0.25초) + 여유
BATCH_SIZE = 200  # IGDB 한 번에 최대 500건. 응답 크기를 고려해 200건씩
MAX_RETRIES = 3  # 429·5xx 재시도 횟수 (지수 백오프)
DEFAULT_GAMES_FILE = (
    Path(__file__).resolve().parents[3] / "analysis" / "game_list" / "games_1000.csv"
)

# 정제기(pipeline/refiner/rules/game.py, links.py)와 docs/collector-test/column-mapping.md가
# 쓰는 필드를 모두 요청한다. 하위 객체는 이름까지 펼친다.
GAME_FIELDS = ",".join(
    [
        "name",
        "slug",
        "summary",
        "game_type",
        "first_release_date",
        "total_rating",
        "total_rating_count",
        "aggregated_rating",
        "aggregated_rating_count",
        "parent_game",
        "version_parent",
        "dlcs",
        "expansions",
        "remakes",
        "remasters",
        "bundles",
        "cover.image_id",
        "platforms.name",
        "genres.name",
        "themes.name",
        "game_modes.name",
        "player_perspectives.name",
        "keywords.name",
        "collections.name",
        "franchises.name",
        "involved_companies.developer",
        "involved_companies.publisher",
        "involved_companies.company.name",
        "external_games.external_game_source",
        "external_games.uid",
        "external_games.url",
        "release_dates.date",
        "release_dates.platform.name",
        "game_localizations.name",
        "game_localizations.region.name",
        "alternative_names.name",
        "alternative_names.comment",
        "age_ratings.*",
    ]
)
TTB_FIELDS = "game_id,hastily,normally,completely,count"


class IgdbError(RuntimeError):
    pass


class IgdbClient:
    """Twitch 토큰을 받아 IGDB를 호출한다. 초당 4회 제한과 재시도를 여기서 강제한다."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        session: requests.Session | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not client_id or not client_secret:
            raise IgdbError("TWITCH_CLIENT_ID / TWITCH_CLIENT_SECRET 이 비어 있다 (.env 확인)")
        self._id = client_id
        self._secret = client_secret
        self._s = session or requests.Session()
        self._sleep = sleep
        self._clock = clock
        self._token: str | None = None
        self._last_call = float("-inf")

    @classmethod
    def from_settings(cls) -> IgdbClient:
        s = get_settings()
        return cls(s.twitch_client_id, s.twitch_client_secret)

    def _refresh_token(self) -> None:
        r = self._s.post(
            TOKEN_URL,
            data={
                "client_id": self._id,
                "client_secret": self._secret,
                "grant_type": "client_credentials",
            },
            timeout=30,
        )
        if not r.ok:  # 응답 본문에 키가 섞일 수 있어 상태 코드만 남긴다
            raise IgdbError(f"Twitch 토큰 발급 실패: HTTP {r.status_code}")
        self._token = r.json()["access_token"]

    def _throttle(self) -> None:
        wait = MIN_INTERVAL_SEC - (self._clock() - self._last_call)
        if wait > 0:
            self._sleep(wait)
        self._last_call = self._clock()

    def query(self, endpoint: str, body: str) -> list[dict[str, Any]]:
        """POST /v4/<endpoint> (Apicalypse 본문). 응답 JSON 원본을 그대로 돌려준다."""
        if self._token is None:
            self._refresh_token()
        refreshed = False
        for attempt in range(MAX_RETRIES + 1):
            self._throttle()
            r = self._s.post(
                f"{API_URL}/{endpoint}",
                headers={
                    "Client-ID": self._id,
                    "Authorization": f"Bearer {self._token}",
                    "User-Agent": USER_AGENT,
                },
                data=body.encode("utf-8"),
                timeout=30,
            )
            if r.status_code == 401 and not refreshed:  # 토큰 만료 → 한 번만 재발급
                refreshed = True
                self._refresh_token()
                continue
            if r.status_code == 429 or r.status_code >= 500:
                if attempt == MAX_RETRIES:
                    break
                delay = 2 ** (attempt + 1)
                log.warning(
                    "IGDB %s HTTP %s, %ss 후 재시도 (%s/%s)",
                    endpoint,
                    r.status_code,
                    delay,
                    attempt + 1,
                    MAX_RETRIES,
                )
                self._sleep(delay)
                continue
            if not r.ok:
                raise IgdbError(f"IGDB {endpoint} HTTP {r.status_code}: {r.text[:200]}")
            return r.json()
        raise IgdbError(f"IGDB {endpoint} 재시도 초과")


def load_game_ids(path: Path = DEFAULT_GAMES_FILE, limit: int | None = None) -> list[int]:
    """games_1000.csv의 game_id(= IGDB ID)를 순서대로 읽는다 (rank 순, 중복 제거)."""
    ids: list[int] = []
    seen: set[int] = set()
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            gid = int(row["game_id"])
            if gid not in seen:
                seen.add(gid)
                ids.append(gid)
    return ids[:limit] if limit else ids


def _chunks(items: list[int], size: int) -> Iterator[list[int]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


def collect(
    game_ids: list[int], client: IgdbClient | None = None
) -> Iterator[tuple[str, RawEnvelope]]:
    """게임 ID 목록 → (Kafka 키, 봉투). 게임 정보를 먼저, 클리어 시간을 그다음에 낸다.

    호출이 실패하면 IgdbError가 올라간다. 그때까지 낸 봉투는 호출 쪽에서 이미 보냈다.
    """
    client = client or IgdbClient.from_settings()

    got: set[int] = set()
    for chunk in _chunks(game_ids, BATCH_SIZE):
        body = (
            f"fields {GAME_FIELDS}; where id = ({','.join(map(str, chunk))}); limit {len(chunk)};"
        )
        for g in client.query("games", body):
            got.add(g["id"])
            yield (
                str(g["id"]),
                RawEnvelope(
                    source="igdb",
                    kind="game_info",
                    request={"url": f"{API_URL}/games", "params": {"body": body}},
                    payload=g,
                ),
            )
    missing = [i for i in game_ids if i not in got]
    if missing:
        log.warning("IGDB가 돌려주지 않은 게임 %d건: %s", len(missing), missing[:20])

    ttb = 0
    for chunk in _chunks(game_ids, BATCH_SIZE):
        body = (
            f"fields {TTB_FIELDS}; where game_id = ({','.join(map(str, chunk))}); "
            f"limit {len(chunk)};"
        )
        for row in client.query("game_time_to_beats", body):
            ttb += 1
            yield (
                str(row["game_id"]),
                RawEnvelope(
                    source="igdb",
                    kind="time_to_beat",
                    request={"url": f"{API_URL}/game_time_to_beats", "params": {"body": body}},
                    payload=row,
                ),
            )
    log.info("IGDB 수집 완료: 게임 %d/%d건, 클리어 시간 %d건", len(got), len(game_ids), ttb)
