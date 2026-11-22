import logging
from datetime import UTC, datetime, timedelta, timezone
from typing import Annotated

import pytest
import redis
from app.api.deps import CurrentUser, get_current_user
from app.core import config, keys
from app.core.errors import register_error_handlers
from app.core.timeutil import UtcDatetime, to_utc_iso
from app.main import lifespan
from app.services import session_store
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel


class FakeValkey:
    def __init__(self, data: dict[str, str] | None = None, down: bool = False) -> None:
        self.data, self.down = data or {}, down

    def get(self, key: str) -> str | None:
        if self.down:
            raise redis.ConnectionError("down")
        return self.data.get(key)


@pytest.fixture
def make_client(monkeypatch: pytest.MonkeyPatch):
    def _make(valkey: FakeValkey, fake_user: bool = False) -> TestClient:
        monkeypatch.setattr(session_store, "get_valkey", lambda: valkey)
        settings = config.BackendSettings(auth_fake_user=fake_user, auth_fake_user_id=7)
        monkeypatch.setattr("app.api.deps.get_backend_settings", lambda: settings)

        app = FastAPI()
        register_error_handlers(app)

        @app.get("/me")
        def me(user: Annotated[CurrentUser, Depends(get_current_user)]) -> dict:
            return {"user_id": user.user_id, "is_fake": user.is_fake}

        return TestClient(app)

    return _make


def _cookie(sid: str) -> dict[str, str]:
    return {keys.SESSION_COOKIE_NAME: sid}


def test_no_session_is_401(make_client) -> None:
    r = make_client(FakeValkey()).get("/me")
    assert r.status_code == 401
    assert r.json() == {"error": {"code": "UNAUTHORIZED", "message": "로그인이 필요합니다"}}


def test_valid_session(make_client) -> None:
    client = make_client(FakeValkey({keys.session_key("abc"): "42"}))
    r = client.get("/me", cookies=_cookie("abc"))
    assert r.json() == {"user_id": 42, "is_fake": False}


def test_unknown_or_malformed_session_is_401(make_client) -> None:
    client = make_client(FakeValkey({keys.session_key("bad"): "not-a-number"}))
    assert client.get("/me", cookies=_cookie("nope")).status_code == 401
    assert client.get("/me", cookies=_cookie("bad")).status_code == 401
    assert client.get("/me", cookies=_cookie("x" * 500)).status_code == 401


def test_valkey_down_is_503_not_401(make_client) -> None:
    r = make_client(FakeValkey(down=True)).get("/me", cookies=_cookie("abc"))
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "UNAVAILABLE"


def test_fake_user_only_when_flag_on_and_no_cookie(make_client) -> None:
    on = make_client(FakeValkey(), fake_user=True)
    assert on.get("/me").json() == {"user_id": 7, "is_fake": True}
    # 쿠키가 있으면 가짜 사용자로 대체하지 않는다
    assert on.get("/me", cookies=_cookie("nope")).status_code == 401
    # 꺼져 있으면 401
    assert make_client(FakeValkey(), fake_user=False).get("/me").status_code == 401


def test_fake_user_default_is_off() -> None:
    assert config.BackendSettings().auth_fake_user is False


def test_startup_warns_when_fake_user_on(monkeypatch: pytest.MonkeyPatch, caplog) -> None:
    monkeypatch.setattr(
        "app.main.get_backend_settings", lambda: config.BackendSettings(auth_fake_user=True)
    )
    app = FastAPI(lifespan=lifespan)
    with caplog.at_level(logging.WARNING), TestClient(app):
        pass
    assert any("AUTH_FAKE_USER" in m for m in caplog.messages)


def test_keys_follow_rules() -> None:
    assert keys.session_key("s1") == "session:s1"
    assert keys.price_cache_key(119133) == "cache:prices:119133"
    assert keys.alert_sent_key(3, 30000) == "alert_sent:3:30000"
    assert keys.spec_check_key(1, "h") == "spec_check:1:h"
    assert keys.PRICE_CACHE_TTL_SECONDS == 600


def test_utc_iso_z() -> None:
    assert to_utc_iso(datetime(2026, 11, 19, 2, 30, 0)) == "2026-11-19T02:30:00Z"
    kst = datetime(2026, 11, 19, 11, 30, 0, tzinfo=timezone(timedelta(hours=9)))
    assert to_utc_iso(kst) == "2026-11-19T02:30:00Z"


def test_utc_datetime_serializes_with_z() -> None:
    class Out(BaseModel):
        created_at: UtcDatetime

    out = Out(created_at=datetime(2026, 11, 19, 2, 30, tzinfo=UTC))
    assert out.model_dump(mode="json") == {"created_at": "2026-11-19T02:30:00Z"}


def test_validation_error_uses_api_error_format() -> None:
    app = FastAPI()
    register_error_handlers(app)

    class Body(BaseModel):
        game_id: int

    @app.post("/x")
    def x(body: Body) -> dict:
        return {}

    r = TestClient(app).post("/x", json={"game_id": "secret-value"})
    assert r.status_code == 422
    assert r.json() == {
        "error": {"code": "INVALID_REQUEST", "message": "요청 값이 올바르지 않습니다: game_id"}
    }
    assert "secret-value" not in r.text
