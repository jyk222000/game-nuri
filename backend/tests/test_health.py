import pytest
from app.main import app
from app.services import health as checks
from fastapi.testclient import TestClient


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _set(monkeypatch: pytest.MonkeyPatch, **results: str) -> None:
    for name, value in results.items():
        monkeypatch.setattr(checks, f"check_{name}", lambda v=value: v)


def test_all_ok(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _set(monkeypatch, db_write="ok", db_read="ok", valkey="ok", es="ok")
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_es_down_is_degraded(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _set(monkeypatch, db_write="ok", db_read="ok", valkey="ok", es="down")
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "degraded"
    assert r.json()["es"] == "down"


def test_valkey_down_is_degraded(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _set(monkeypatch, db_write="ok", db_read="ok", valkey="down", es="ok")
    assert client.get("/api/health").json()["status"] == "degraded"


@pytest.mark.parametrize("failed", ["db_write", "db_read"])
def test_db_down_is_503(client: TestClient, monkeypatch: pytest.MonkeyPatch, failed: str) -> None:
    results = {"db_write": "ok", "db_read": "ok", "valkey": "ok", "es": "ok"}
    results[failed] = "down"
    _set(monkeypatch, **results)
    r = client.get("/api/health")
    assert r.status_code == 503
    assert r.json()["status"] == "down"


def test_metrics_exposed(client: TestClient) -> None:
    assert client.get("/metrics").status_code == 200


def test_app_starts_without_services(client: TestClient) -> None:
    # 실제 DB·Valkey·ES가 없어도 요청이 예외 없이 503으로 끝나야 한다.
    r = client.get("/api/health")
    assert r.status_code == 503
    assert r.json()["valkey"] == "down"
