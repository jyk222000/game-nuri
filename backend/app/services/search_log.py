"""실시간 검색어(#34)·최근 검색어(#35). 클릭스트림(ES `clickstream-*`)의 `search` 이벤트를 읽는다.

데이터 흐름: 화면의 검색 → POST /api/events → Kafka `clickstream` → Kafka Connect → ES.
여기서는 ES를 읽기만 한다. ES가 안 돼도 500을 내지 않고 빈 목록을 돌려준다(화면이 멈추지 않게).

- 실시간 검색어: 최근 1시간의 검색어를 세어 상위 10개. 바로 앞 1시간과 순위를 비교해 change를 정함.
  `GTA`/`gta`/`G T A`처럼 대소문자·공백만 다른 검색어는 한 검색어로 합쳐 센다.
- 최근 검색어: 내 user_id의 가장 최근 검색어를 최신순으로, 중복 없이.
- 결과(실시간 검색어)는 Valkey에 1분 저장한다. Valkey가 죽어도 ES에서 바로 읽는다.
"""

import logging
from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Literal

import redis
from elasticsearch import ApiError, TransportError
from pydantic import ValidationError

from app.clients.es import get_es
from app.clients.valkey import get_valkey
from app.core import keys
from app.schemas.search_log import RecentOut, TrendingItem, TrendingOut

log = logging.getLogger(__name__)

INDEX = "clickstream-*"
WINDOW = timedelta(hours=1)
WINDOW_LABEL = "1h"
TRENDING_SIZE = 10
CANDIDATES = 100  # 합치기 전에 구간마다 가져올 검색어 수 (공백·대소문자 변형이 합쳐질 여유)
RECENT_SIZE = 10
RECENT_FETCH = 50  # 중복을 지우기 전에 가져올 최신 검색 수


def normalize(query: str) -> str:
    """같은 검색어로 볼 키: 공백을 모두 지우고 소문자로."""
    return "".join(query.split()).casefold()


def _iso(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def merge_counts(buckets: list[dict]) -> dict[str, tuple[str, int]]:
    """ES 버킷을 정규화 키로 합친다 → {키: (보여 줄 검색어, 합친 횟수)}.

    보여 줄 검색어는 가장 많이 쓰인 원래 표기(같으면 사전순 앞)다.
    """
    counts: Counter[str] = Counter()
    variants: dict[str, Counter[str]] = {}
    for bucket in buckets:
        raw = str(bucket["key"])
        key = normalize(raw)
        if not key:
            continue
        n = int(bucket["doc_count"])
        counts[key] += n
        variants.setdefault(key, Counter())[raw] += n
    merged = {}
    for key, total in counts.items():
        shown = min(variants[key].items(), key=lambda kv: (-kv[1], kv[0]))[0]
        merged[key] = (shown, total)
    return merged


def _ranked(merged: dict[str, tuple[str, int]]) -> list[str]:
    """많이 검색된 순, 같으면 키 순. 키 목록을 순위대로."""
    return sorted(merged, key=lambda k: (-merged[k][1], k))


def build_trending(current: list[dict], previous: list[dict]) -> TrendingOut:
    cur, prev = merge_counts(current), merge_counts(previous)
    prev_rank = {key: i for i, key in enumerate(_ranked(prev), start=1)}
    items = []
    for rank, key in enumerate(_ranked(cur)[:TRENDING_SIZE], start=1):
        before = prev_rank.get(key)
        change: Literal["up", "down", "same", "new"]
        if before is None:
            change = "new"
        elif rank < before:
            change = "up"
        elif rank > before:
            change = "down"
        else:
            change = "same"
        shown, count = cur[key]
        items.append(TrendingItem(rank=rank, query=shown, count=count, change=change))
    return TrendingOut(window=WINDOW_LABEL, items=items)


def _empty() -> TrendingOut:
    return TrendingOut(window=WINDOW_LABEL, items=[])


# ---------- 캐시 (fail-open) ----------
def _cache_get() -> TrendingOut | None:
    try:
        raw = get_valkey().get(keys.trending_cache_key())
    except redis.RedisError as exc:
        log.warning("검색어 캐시 읽기 실패, ES로 진행: %s", type(exc).__name__)
        return None
    if raw is None:
        return None
    try:
        return TrendingOut.model_validate_json(raw)
    except ValidationError:
        log.warning("검색어 캐시 값이 올바르지 않아 무시함")
        return None


def _cache_set(value: TrendingOut) -> None:
    try:
        get_valkey().set(
            keys.trending_cache_key(), value.model_dump_json(), ex=keys.TRENDING_CACHE_TTL_SECONDS
        )
    except redis.RedisError as exc:
        log.warning("검색어 캐시 쓰기 실패, 건너뜀: %s", type(exc).__name__)


# ---------- #34 실시간 검색어 ----------
def get_trending(now: datetime | None = None) -> TrendingOut:
    cached = _cache_get()
    if cached is not None:
        return cached

    now = now or datetime.now(UTC)
    t_cur, t_prev = now - WINDOW, now - 2 * WINDOW
    terms = {"terms": {"field": "query", "size": CANDIDATES}}
    try:
        result = get_es().search(
            index=INDEX,
            size=0,
            query={
                "bool": {
                    "filter": [
                        {"term": {"event": "search"}},
                        {"range": {"occurred_at": {"gte": _iso(t_prev), "lt": _iso(now)}}},
                    ]
                }
            },
            aggs={
                "windows": {
                    "filters": {
                        "filters": {
                            "cur": {"range": {"occurred_at": {"gte": _iso(t_cur)}}},
                            "prev": {
                                "range": {"occurred_at": {"gte": _iso(t_prev), "lt": _iso(t_cur)}}
                            },
                        }
                    },
                    "aggs": {"q": terms},
                }
            },
        )
        buckets = result["aggregations"]["windows"]["buckets"]
        out = build_trending(buckets["cur"]["q"]["buckets"], buckets["prev"]["q"]["buckets"])
    except (ApiError, TransportError, KeyError) as exc:
        log.warning("실시간 검색어 조회 실패, 빈 목록으로 응답: %s", type(exc).__name__)
        return _empty()  # 장애 결과는 캐시에 넣지 않는다
    _cache_set(out)
    return out


# ---------- #35 최근 검색어 ----------
def get_recent(user_id: int) -> RecentOut:
    try:
        result = get_es().search(
            index=INDEX,
            size=RECENT_FETCH,
            query={
                "bool": {
                    "filter": [
                        {"term": {"event": "search"}},
                        {"term": {"user_id": str(user_id)}},
                    ]
                }
            },
            sort=[{"occurred_at": "desc"}],
            source_includes=["query"],
        )
        hits = result["hits"]["hits"]
    except (ApiError, TransportError, KeyError) as exc:
        log.warning("최근 검색어 조회 실패, 빈 목록으로 응답: %s", type(exc).__name__)
        return RecentOut(items=[])

    seen: set[str] = set()
    items: list[str] = []
    for hit in hits:
        query = hit.get("_source", {}).get("query")
        key = normalize(query) if query else ""
        if not key or key in seen:
            continue
        seen.add(key)
        items.append(query)
        if len(items) == RECENT_SIZE:
            break
    return RecentOut(items=items)
