"""#34 실시간 검색어, #35 최근 검색어. ES·Valkey는 가짜로 확인한다(응답 모양은 실제 ES와 같게)."""

from datetime import UTC, datetime

import pytest
import redis
from app.main import app
from app.services import search_log
from elastic_transport import ConnectionError as EsConnectionError
from fastapi.testclient import TestClient


def _agg(cur: list[tuple[str, int]], prev: list[tuple[str, int]] | None = None) -> dict:
    """ES filters 집계 응답 모양: aggregations.windows.buckets.{cur,prev}.q.buckets."""

    def buckets(pairs):  # noqa: ANN001, ANN202
        return {"q": {"buckets": [{"key": k, "doc_count": n} for k, n in pairs]}}

    return {
        "aggregations": {"windows": {"buckets": {"cur": buckets(cur), "prev": buckets(prev or [])}}}
    }


def _hits(*queries: str | None) -> dict:
    return {"hits": {"hits": [{"_source": {"query": q} if q is not None else {}} for q in queries]}}


class FakeEs:
    def __init__(self, result: dict | None = None, error: Exception | None = None) -> None:
        self.result, self.error = result, error
        self.calls: list[dict] = []

    def search(self, **kwargs):  # noqa: ANN003
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.result


class FakeValkey:
    def __init__(self) -> None:
        self.data: dict[str, str] = {}
        self.ttl: dict[str, int] = {}

    def get(self, key):  # noqa: ANN001
        return self.data.get(key)

    def set(self, key, value, ex=None):  # noqa: ANN001
        self.data[key] = value
        self.ttl[key] = ex


class DeadValkey:
    def get(self, key):  # noqa: ANN001
        raise redis.ConnectionError("down")

    def set(self, key, value, ex=None):  # noqa: ANN001
        raise redis.ConnectionError("down")


@pytest.fixture
def valkey(monkeypatch):  # noqa: ANN001
    v = FakeValkey()
    monkeypatch.setattr(search_log, "get_valkey", lambda: v)
    return v


def use_es(monkeypatch, es: FakeEs) -> FakeEs:  # noqa: ANN001
    monkeypatch.setattr(search_log, "get_es", lambda: es)
    return es


# ---------- 순수 계산 ----------
def test_normalize_ignores_case_and_spaces() -> None:
    assert search_log.normalize(" G T A ") == search_log.normalize("gta") == "gta"
    assert search_log.normalize("엘든 링") == search_log.normalize("엘든링")
    assert search_log.normalize("   ") == ""


def test_merge_counts_joins_variants_and_shows_most_used_spelling() -> None:
    merged = search_log.merge_counts(
        [
            {"key": "GTA", "doc_count": 2},
            {"key": "gta", "doc_count": 5},
            {"key": "G T A", "doc_count": 1},
            {"key": "  ", "doc_count": 9},  # 공백뿐인 검색어는 버린다
        ]
    )
    assert merged == {"gta": ("gta", 8)}


def test_rank_ties_break_by_query_and_change_is_computed_against_previous_window() -> None:
    out = search_log.build_trending(
        current=[
            {"key": "하데스", "doc_count": 9},
            {"key": "엘든 링", "doc_count": 5},
            {"key": "포르자", "doc_count": 5},  # 엘든 링과 같은 횟수: 키 순
            {"key": "신작", "doc_count": 1},
        ],
        previous=[
            {"key": "엘든링", "doc_count": 20},  # 공백만 다른 같은 검색어, 이전 1위
            {"key": "하데스", "doc_count": 3},  # 이전 2위
            {"key": "포르자", "doc_count": 2},  # 이전 3위
        ],
    )
    got = [(i.rank, i.query, i.count, i.change) for i in out.items]
    assert got == [
        (1, "하데스", 9, "up"),  # 2위 → 1위
        (2, "엘든 링", 5, "down"),  # 1위 → 2위
        (3, "포르자", 5, "same"),  # 3위 → 3위
        (4, "신작", 1, "new"),  # 이전에 없음
    ]
    assert out.window == "1h"


def test_trending_keeps_top_10_only() -> None:
    current = [{"key": f"게임{i:02d}", "doc_count": 100 - i} for i in range(25)]
    out = search_log.build_trending(current, [])
    assert [i.rank for i in out.items] == list(range(1, 11)) and out.items[0].query == "게임00"


# ---------- #34 API ----------
def test_trending_api_shape_and_es_query(env, valkey, monkeypatch) -> None:  # noqa: ANN001
    client, *_ = env
    es = use_es(monkeypatch, FakeEs(_agg([("GTA", 2), ("그타", 1), ("포르자", 1)])))  # 실제 ES 응답
    body = client.get("/api/search/trending").json()
    assert body["window"] == "1h"
    assert [(i["rank"], i["query"], i["count"], i["change"]) for i in body["items"]] == [
        (1, "GTA", 2, "new"),
        (2, "그타", 1, "new"),
        (3, "포르자", 1, "new"),
    ]
    call = es.calls[0]
    assert call["index"] == "clickstream-*" and call["size"] == 0
    assert {"term": {"event": "search"}} in call["query"]["bool"]["filter"]  # 검색 이벤트만


def test_trending_time_ranges_use_now(valkey, monkeypatch) -> None:  # noqa: ANN001
    es = use_es(monkeypatch, FakeEs(_agg([])))
    search_log.get_trending(now=datetime(2026, 11, 24, 9, 0, 0, tzinfo=UTC))
    filters = es.calls[0]["aggs"]["windows"]["filters"]["filters"]
    assert filters["cur"]["range"]["occurred_at"] == {"gte": "2026-11-24T08:00:00Z"}
    assert filters["prev"]["range"]["occurred_at"] == {
        "gte": "2026-11-24T07:00:00Z",
        "lt": "2026-11-24T08:00:00Z",
    }
    outer = es.calls[0]["query"]["bool"]["filter"][1]["range"]["occurred_at"]
    assert outer == {"gte": "2026-11-24T07:00:00Z", "lt": "2026-11-24T09:00:00Z"}


def test_trending_empty_when_nobody_searched(env, valkey, monkeypatch) -> None:  # noqa: ANN001
    client, *_ = env
    use_es(monkeypatch, FakeEs(_agg([])))
    assert client.get("/api/search/trending").json() == {"window": "1h", "items": []}


def test_trending_is_cached_for_a_minute(env, valkey, monkeypatch) -> None:  # noqa: ANN001
    client, *_ = env
    es = use_es(monkeypatch, FakeEs(_agg([("GTA", 2)])))
    first = client.get("/api/search/trending").json()
    second = client.get("/api/search/trending").json()
    assert first == second and len(es.calls) == 1  # 두 번째는 Valkey에서
    assert list(valkey.ttl.values()) == [60]


def test_trending_works_when_valkey_is_down(env, monkeypatch) -> None:  # noqa: ANN001
    client, *_ = env
    monkeypatch.setattr(search_log, "get_valkey", lambda: DeadValkey())
    use_es(monkeypatch, FakeEs(_agg([("GTA", 2)])))
    r = client.get("/api/search/trending")
    assert r.status_code == 200 and r.json()["items"][0]["query"] == "GTA"


@pytest.mark.parametrize("error", [EsConnectionError("down"), KeyError("aggregations")])
def test_trending_es_failure_is_empty_200_and_not_cached(env, valkey, monkeypatch, error) -> None:  # noqa: ANN001
    client, *_ = env
    es = use_es(monkeypatch, FakeEs(error=error))
    r = client.get("/api/search/trending")
    assert r.status_code == 200 and r.json() == {"window": "1h", "items": []}
    assert valkey.data == {}  # 장애 결과를 1분 동안 붙잡아 두지 않는다
    client.get("/api/search/trending")
    assert len(es.calls) == 2


def test_trending_needs_no_login(valkey, monkeypatch) -> None:  # noqa: ANN001
    app.dependency_overrides.clear()  # 가짜 로그인 꺼짐: 세션 없이 호출한다
    use_es(monkeypatch, FakeEs(_agg([("GTA", 2)])))
    r = TestClient(app).get("/api/search/trending")
    assert r.status_code == 200 and r.json()["items"][0]["query"] == "GTA"  # 401이면 안 된다


# ---------- #35 API ----------
def test_recent_returns_latest_first_without_duplicates(env, monkeypatch) -> None:  # noqa: ANN001
    client, *_ = env
    es = use_es(monkeypatch, FakeEs(_hits("그타", "GTA", "gta", "G T A", "포르자", "GTA")))
    assert client.get("/api/search/recent").json() == {"items": ["그타", "GTA", "포르자"]}
    call = es.calls[0]
    assert {"term": {"user_id": "1"}} in call["query"]["bool"]["filter"]  # 내 검색만 (env 사용자 1)
    assert {"term": {"event": "search"}} in call["query"]["bool"]["filter"]
    assert call["sort"] == [{"occurred_at": "desc"}]
    assert call["source_includes"] == ["query"]  # 검색어 문자열만 가져온다


def test_recent_is_per_user(env, monkeypatch) -> None:  # noqa: ANN001
    client, _, current = env
    es = use_es(monkeypatch, FakeEs(_hits("하데스")))
    current["id"] = 2
    client.get("/api/search/recent")
    assert {"term": {"user_id": "2"}} in es.calls[0]["query"]["bool"]["filter"]


def test_recent_keeps_10_and_skips_blank_entries(env, monkeypatch) -> None:  # noqa: ANN001
    client, *_ = env
    queries = [None, "  "] + [f"검색{i}" for i in range(20)]
    use_es(monkeypatch, FakeEs(_hits(*queries)))
    items = client.get("/api/search/recent").json()["items"]
    assert items == [f"검색{i}" for i in range(10)]


def test_recent_es_failure_is_empty_200(env, monkeypatch) -> None:  # noqa: ANN001
    client, *_ = env
    use_es(monkeypatch, FakeEs(error=EsConnectionError("down")))
    r = client.get("/api/search/recent")
    assert r.status_code == 200 and r.json() == {"items": []}


def test_recent_requires_login() -> None:
    app.dependency_overrides.clear()  # 가짜 사용자 꺼짐(기본)이라 세션 없이는 401
    r = TestClient(app).get("/api/search/recent")
    assert r.status_code == 401 and r.json()["error"]["code"] == "UNAUTHORIZED"
