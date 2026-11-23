"""#37 API 사용 순위: Prometheus HTTP API 조회, 실패하면 빈 목록 + degraded."""

import httpx
import pytest
from app.clients import prometheus
from app.core.config import get_backend_settings
from app.main import app
from fastapi.testclient import TestClient


def _sample(handler, method, value):
    return {"metric": {"handler": handler, "method": method}, "value": [1700000000, value]}


@pytest.fixture
def client(monkeypatch):
    app.dependency_overrides.clear()
    monkeypatch.setenv("PROMETHEUS_URL", "http://monitoring:9090")
    get_backend_settings.cache_clear()
    yield TestClient(app)
    get_backend_settings.cache_clear()


def _fake_get(result=None, exc=None, status="success", seen=None):
    def get(url, params=None, timeout=None):  # noqa: ANN001
        if seen is not None:
            seen.update(url=url, params=params, timeout=timeout)
        if exc:
            raise exc
        req = httpx.Request("GET", url)
        return httpx.Response(
            200, json={"status": status, "data": {"result": result or []}}, request=req
        )

    return get


def test_ranking_sorted_with_rank_and_queries_prometheus(client, monkeypatch) -> None:
    seen: dict = {}
    result = [
        _sample("/api/games", "GET", "18240.4"),
        _sample("/api/games/{game_id}", "GET", "30000"),
        _sample("/api/events", "POST", "18240"),  # 동점은 이름순
        _sample("/api/me/alerts", "POST", "0"),  # 0건은 뺀다
        {"metric": {}, "value": [1, "5"]},  # 모양이 다른 항목은 건너뛴다
    ]
    monkeypatch.setattr(httpx, "get", _fake_get(result, seen=seen))
    body = client.get("/api/stats/api-ranking").json()
    assert body["status"] == "ok"
    assert body["items"] == [
        {"rank": 1, "api": "GET /api/games/{game_id}", "calls": 30000},
        {"rank": 2, "api": "GET /api/games", "calls": 18240},
        {"rank": 3, "api": "POST /api/events", "calls": 18240},
    ]
    assert seen["url"] == "http://monitoring:9090/api/v1/query"
    assert "http_requests_total" in seen["params"]["query"] and seen["timeout"] <= 2


def test_size_limits_items(client, monkeypatch) -> None:
    result = [_sample(f"/api/x{i}", "GET", str(10 + i)) for i in range(5)]
    monkeypatch.setattr(httpx, "get", _fake_get(result))
    items = client.get("/api/stats/api-ranking?size=2").json()["items"]
    assert [i["rank"] for i in items] == [1, 2]


@pytest.mark.parametrize(
    "fake",
    [
        _fake_get(exc=httpx.ConnectError("down")),
        _fake_get(exc=httpx.ReadTimeout("slow")),
        _fake_get(status="error"),
    ],
)
def test_prometheus_failure_is_empty_and_degraded(client, monkeypatch, fake) -> None:
    monkeypatch.setattr(httpx, "get", fake)
    r = client.get("/api/stats/api-ranking")
    assert r.status_code == 200 and r.json() == {"items": [], "status": "degraded"}


def test_no_url_configured_is_degraded(monkeypatch) -> None:
    app.dependency_overrides.clear()
    monkeypatch.setenv("PROMETHEUS_URL", "")
    get_backend_settings.cache_clear()
    try:
        r = TestClient(app).get("/api/stats/api-ranking")
    finally:
        get_backend_settings.cache_clear()
    assert r.json() == {"items": [], "status": "degraded"}
    assert prometheus.TIMEOUT_SECONDS <= 2


def test_size_validation(client) -> None:
    assert client.get("/api/stats/api-ranking?size=0").status_code == 422
    assert client.get("/api/stats/api-ranking?size=51").status_code == 422
