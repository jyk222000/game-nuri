"""ITAD: POST /games/prices/v3 (country=KR) → raw.price

수집 대상은 `analysis/game_list/games_1000.csv`의 `itad_id` (Steam appid로 미리 조회해 둔 값).
응답은 가공하지 않고 봉투(payload)에 그대로 담는다.
게임 1건 = 봉투 1개 (`{id, historyLow, deals[]}`).

- 키는 쿼리 파라미터(`key`)로 가므로 URL·예외 문구에 절대 넣지 않는다.
- 한도는 5분당 1,000건. 한 번에 여러 게임을 보내므로 1,000게임이 10회 안팎이다.
- 가격 이력(`games/history/v2`, USD)은 정제기에 받는 쪽(kind)이 없어 이번 범위에서 뺐다.
"""

from __future__ import annotations

import csv
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
from gamenuri_common.config import get_settings
from gamenuri_common.logging import get_logger
from gamenuri_common.messages import RawEnvelope

log = get_logger("collector.itad")

API_URL = "https://api.isthereanydeal.com"
PRICES_PATH = "/games/prices/v3"
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
        for attempt in range(MAX_RETRIES + 1):
            self._throttle()
            r = self._s.post(
                API_URL + path,
                params={"key": self._key, **params},
                json=body,
                headers={"User-Agent": USER_AGENT},
                timeout=30,
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
