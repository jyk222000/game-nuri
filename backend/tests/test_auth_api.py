"""구글 로그인 라우터(/api/auth/*). 구글·Valkey는 가짜, DB는 SQLite 메모리.

Secure 쿠키는 https 주소로만 되돌아오므로 클라이언트를 https로 만든다.
"""

from urllib.parse import parse_qs, urlparse

import pytest
from app.api import deps
from app.core import config
from app.core.keys import SESSION_COOKIE_NAME, SESSION_TTL_SECONDS, session_key
from app.db.base import Base
from app.db.models import User
from app.db.session import get_write_db
from app.main import app
from app.services import auth, session_store
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

PROFILE = auth.GoogleProfile(sub="sub-1", email="new@example.com", name="한예찬")
STATE_COOKIE = auth.STATE_COOKIE_NAME


def _settings(**over) -> config.BackendSettings:  # noqa: ANN003
    values = dict(
        google_client_id="cid",
        google_client_secret="csecret",
        google_redirect_uri="https://gamenuri.store/api/auth/google/callback",
        session_secret="test-session-secret",
    )
    values.update(over)
    return config.BackendSettings(_env_file=None, **values)


class FakeValkey:
    def __init__(self) -> None:
        self.data: dict[str, str] = {}
        self.ttl: dict[str, int] = {}

    def set(self, key, value, ex=None):  # noqa: ANN001
        self.data[key] = value
        if ex:
            self.ttl[key] = ex

    def get(self, key):  # noqa: ANN001
        return self.data.get(key)

    def delete(self, key):  # noqa: ANN001
        self.data.pop(key, None)

    def expire(self, key, seconds):  # noqa: ANN001
        if key not in self.data:
            return False
        self.ttl[key] = seconds
        return True


@pytest.fixture
def web(monkeypatch):  # noqa: ANN001
    """(client, engine, valkey). 로그인 설정이 채워져 있고 구글 응답은 PROFILE로 고정."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)

    def db():
        with Session(engine) as s:
            yield s

    valkey = FakeValkey()
    monkeypatch.setattr(auth, "get_valkey", lambda: valkey)
    monkeypatch.setattr(session_store, "get_valkey", lambda: valkey)
    monkeypatch.setattr(auth, "get_backend_settings", lambda: _settings())
    monkeypatch.setattr(auth, "fetch_google_profile", lambda code, verifier, s=None: PROFILE)
    app.dependency_overrides[get_write_db] = db
    yield TestClient(app, base_url="https://testserver", follow_redirects=False), engine, valkey
    app.dependency_overrides.clear()


def _login(client: TestClient) -> str:
    """로그인 시작 → 콜백까지 끝내고 세션 id를 돌려준다."""
    start = client.get("/api/auth/google/login")
    state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]
    done = client.get("/api/auth/google/callback", params={"code": "c", "state": state})
    assert done.status_code == 302
    return client.cookies[SESSION_COOKIE_NAME]


def _set_cookie(response, name: str) -> str:  # noqa: ANN001
    return next(v for v in response.headers.get_list("set-cookie") if v.startswith(f"{name}="))


def test_login_redirects_to_google_with_state_cookie(web) -> None:
    client, *_ = web
    r = client.get("/api/auth/google/login")
    assert r.status_code == 302
    url = urlparse(r.headers["location"])
    assert url.netloc == "accounts.google.com"
    query = parse_qs(url.query)
    assert query["client_id"] == ["cid"] and query["code_challenge_method"] == ["S256"]
    cookie = _set_cookie(r, STATE_COOKIE).lower()
    assert "httponly" in cookie and "secure" in cookie and "samesite=lax" in cookie
    assert "path=/api/auth" in cookie


def test_login_not_configured_is_503(web, monkeypatch) -> None:  # noqa: ANN001
    client, *_ = web
    monkeypatch.setattr(auth, "get_backend_settings", lambda: _settings(google_client_id=""))
    r = client.get("/api/auth/google/login")
    assert r.status_code == 503 and r.json()["error"]["code"] == "UNAVAILABLE"


def test_callback_creates_user_session_cookie_and_goes_home(web) -> None:
    client, engine, valkey = web
    start = client.get("/api/auth/google/login")
    state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]
    r = client.get("/api/auth/google/callback", params={"code": "c", "state": state})
    assert r.status_code == 302 and r.headers["location"] == "/"
    cookie = _set_cookie(r, SESSION_COOKIE_NAME).lower()
    assert "httponly" in cookie and "secure" in cookie and "path=/" in cookie
    # 임시 state 쿠키는 지워진다
    assert "max-age=0" in _set_cookie(r, STATE_COOKIE).lower()
    with Session(engine) as s:
        user = s.scalars(select(User)).one()
    session_id = client.cookies[SESSION_COOKIE_NAME]
    assert valkey.data[session_key(session_id)] == str(user.user_id)
    assert valkey.ttl[session_key(session_id)] == SESSION_TTL_SECONDS


def test_callback_rejects_wrong_state_and_missing_code(web) -> None:
    client, engine, valkey = web
    client.get("/api/auth/google/login")
    bad = client.get("/api/auth/google/callback", params={"code": "c", "state": "other"})
    assert bad.status_code == 400 and bad.json()["error"]["code"] == "LOGIN_FAILED"
    cancelled = client.get("/api/auth/google/callback", params={"state": "x"})  # 구글에서 취소
    assert cancelled.status_code == 400 and cancelled.json()["error"]["code"] == "LOGIN_FAILED"
    assert valkey.data == {}  # 세션이 만들어지지 않았다
    with Session(engine) as s:
        assert s.scalars(select(User)).all() == []


def test_callback_without_state_cookie_fails(web) -> None:
    client, *_ = web
    r = client.get("/api/auth/google/callback", params={"code": "c", "state": "x"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "LOGIN_FAILED"


def test_logged_in_user_can_call_login_required_api(web) -> None:
    """로그인으로 받은 쿠키가 실제로 다른 API의 로그인 확인(get_current_user)을 통과한다."""
    client, *_ = web
    assert client.get("/api/me").status_code == 401
    _login(client)
    assert client.get("/api/me").status_code == 200


def test_logout_deletes_session_and_cookie(web) -> None:
    client, _, valkey = web
    session_id = _login(client)
    r = client.post("/api/auth/logout")
    assert r.status_code == 200 and r.json() == {"ok": True}
    assert session_key(session_id) not in valkey.data
    assert "max-age=0" in _set_cookie(r, SESSION_COOKIE_NAME).lower()
    assert client.get("/api/me").status_code == 401  # 로그아웃 뒤에는 막힌다


def test_refresh_extends_session_and_cookie(web) -> None:
    client, _, valkey = web
    session_id = _login(client)
    valkey.ttl[session_key(session_id)] = 5
    r = client.post("/api/auth/refresh")
    assert r.status_code == 200 and r.json() == {"ok": True}
    assert valkey.ttl[session_key(session_id)] == SESSION_TTL_SECONDS
    assert f"{SESSION_COOKIE_NAME}={session_id}" in _set_cookie(r, SESSION_COOKIE_NAME)


@pytest.mark.parametrize("path", ["/api/auth/refresh", "/api/auth/logout"])
def test_refresh_and_logout_require_login(web, path) -> None:  # noqa: ANN001
    client, *_ = web
    r = client.post(path)
    assert r.status_code == 401 and r.json()["error"]["code"] == "UNAUTHORIZED"


def test_expired_session_cookie_is_401(web) -> None:
    client, _, valkey = web
    _login(client)
    valkey.data.clear()  # Valkey에서 세션이 사라짐(만료)
    assert client.post("/api/auth/logout").status_code == 401


def test_fake_user_without_cookie_can_logout_without_error(web, monkeypatch) -> None:  # noqa: ANN001
    """개발용 가짜 사용자(쿠키 없음)는 지울 세션이 없어도 오류 없이 ok."""
    client, *_ = web
    monkeypatch.setattr(deps, "get_backend_settings", lambda: _settings(auth_fake_user=True))
    for path in ("/api/auth/logout", "/api/auth/refresh"):
        r = client.post(path)
        assert r.status_code == 200 and r.json() == {"ok": True}
