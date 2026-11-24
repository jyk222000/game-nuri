"""구글 로그인 서비스(app/services/auth.py). 구글·Valkey는 가짜, DB는 SQLite 메모리로 확인한다."""

from datetime import datetime
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from app.core import config
from app.core.errors import ApiError
from app.core.keys import SESSION_TTL_SECONDS, session_key
from app.db.base import Base
from app.db.models import User
from app.services import auth
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

NOW = datetime(2026, 11, 24)
PROFILE = auth.GoogleProfile(sub="sub-1", email="new@example.com", name="한예찬")


def settings(**over) -> config.BackendSettings:  # noqa: ANN003
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

    def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.data[key] = value
        if ex:
            self.ttl[key] = ex

    def get(self, key: str) -> str | None:
        return self.data.get(key)

    def delete(self, key: str) -> None:
        self.data.pop(key, None)

    def expire(self, key: str, seconds: int) -> bool:
        if key not in self.data:
            return False
        self.ttl[key] = seconds
        return True


@pytest.fixture
def valkey(monkeypatch):  # noqa: ANN001
    v = FakeValkey()
    monkeypatch.setattr(auth, "get_valkey", lambda: v)
    return v


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def users(db: Session) -> list[User]:
    return list(db.scalars(select(User)))


def code_error(exc: pytest.ExceptionInfo[ApiError]) -> str:
    return exc.value.code


# ---------- 로그인 시작 ----------
def test_start_login_builds_google_url_with_state_and_pkce() -> None:
    start = auth.start_login(settings())
    url = urlparse(start.url)
    q = {k: v[0] for k, v in parse_qs(url.query).items()}
    assert f"{url.scheme}://{url.netloc}{url.path}" == auth.GOOGLE_AUTH_URL
    assert q["client_id"] == "cid"
    assert q["redirect_uri"] == "https://gamenuri.store/api/auth/google/callback"
    assert q["response_type"] == "code"
    assert q["scope"] == "openid email profile"
    assert q["code_challenge_method"] == "S256"
    assert q["code_challenge"] and q["state"]
    assert "csecret" not in start.url  # 시크릿은 주소에 들어가지 않는다


def test_start_login_state_cookie_carries_state_and_verifier() -> None:
    s = settings()
    start = auth.start_login(s)
    state = parse_qs(urlparse(start.url).query)["state"][0]
    data = auth._serializer(s).loads(start.state_cookie)
    assert data["state"] == state
    assert data["verifier"]  # 시크릿 값은 주소가 아니라 쿠키 안에만 있다
    assert data["verifier"] not in start.url


@pytest.mark.parametrize(
    "missing", ["google_client_id", "google_client_secret", "google_redirect_uri", "session_secret"]
)
def test_start_login_refuses_when_not_configured(missing: str) -> None:
    with pytest.raises(ApiError) as exc:
        auth.start_login(settings(**{missing: ""}))
    assert exc.value.status_code == 503


# ---------- 콜백: state 검증 ----------
def begin(s: config.BackendSettings) -> tuple[str, str]:
    start = auth.start_login(s)
    return parse_qs(urlparse(start.url).query)["state"][0], start.state_cookie


def test_finish_login_rejects_missing_code(db, valkey) -> None:  # noqa: ANN001
    s = settings()
    state, cookie = begin(s)
    with pytest.raises(ApiError) as exc:  # 구글 화면에서 취소한 경우
        auth.finish_login(db, None, state, cookie, s)
    assert code_error(exc) == "LOGIN_FAILED"


@pytest.mark.parametrize(
    "case", ["no_state", "no_cookie", "wrong_state", "tampered", "other_secret"]
)
def test_finish_login_rejects_bad_state(db, valkey, monkeypatch, case) -> None:  # noqa: ANN001
    s = settings()
    state, cookie = begin(s)
    called = []
    monkeypatch.setattr(auth, "fetch_google_profile", lambda *a, **k: called.append(1) or PROFILE)
    args = {
        "no_state": (None, cookie),
        "no_cookie": (state, None),
        "wrong_state": ("other-state", cookie),
        "tampered": (state, cookie[:-2] + "xx"),
        "other_secret": (state, auth._serializer(settings(session_secret="x")).dumps({})),
    }[case]
    with pytest.raises(ApiError) as exc:
        auth.finish_login(db, "code", *args, s)
    assert code_error(exc) == "LOGIN_FAILED"
    assert not called  # 확인에 실패하면 구글에 코드를 보내지 않는다
    assert users(db) == [] and valkey.data == {}


def test_finish_login_rejects_expired_state_cookie(db, valkey, monkeypatch) -> None:  # noqa: ANN001
    s = settings()
    state, cookie = begin(s)
    monkeypatch.setattr(auth, "STATE_MAX_AGE_SECONDS", -1)
    with pytest.raises(ApiError) as exc:
        auth.finish_login(db, "code", state, cookie, s)
    assert code_error(exc) == "LOGIN_FAILED"


# ---------- 콜백: 성공 ----------
def test_finish_login_creates_user_and_session(db, valkey, monkeypatch) -> None:  # noqa: ANN001
    s = settings()
    state, cookie = begin(s)
    seen = {}

    def fake_fetch(code, verifier, _settings=None):  # noqa: ANN001, ANN202
        seen.update(code=code, verifier=verifier)
        return PROFILE

    monkeypatch.setattr(auth, "fetch_google_profile", fake_fetch)
    result = auth.finish_login(db, "the-code", state, cookie, s)

    assert seen["code"] == "the-code"
    assert seen["verifier"] == auth._serializer(s).loads(cookie)["verifier"]
    (user,) = users(db)
    assert (user.email, user.google_sub, user.nickname) == ("new@example.com", "sub-1", "한예찬")
    assert user.password_hash is None
    assert result.user_id == user.user_id
    assert valkey.data[session_key(result.session_id)] == str(user.user_id)
    assert valkey.ttl[session_key(result.session_id)] == SESSION_TTL_SECONDS


def test_second_login_reuses_user_and_keeps_renamed_nickname(db, valkey) -> None:  # noqa: ANN001
    first = auth.upsert_user(db, PROFILE)
    first.nickname = "바꾼 이름"
    db.commit()
    again = auth.upsert_user(db, auth.GoogleProfile("sub-1", "new@example.com", "구글 이름"))
    assert again.user_id == first.user_id
    assert [u.nickname for u in users(db)] == ["바꾼 이름"]


def test_login_links_google_to_existing_email_account(db) -> None:  # noqa: ANN001
    db.add(User(email="old@example.com", nickname="기존", created_at=NOW))
    db.commit()
    user = auth.upsert_user(db, auth.GoogleProfile("sub-9", "old@example.com", "이름"))
    assert user.google_sub == "sub-9" and user.nickname == "기존"
    assert len(users(db)) == 1


def test_nickname_falls_back_to_email_local_part_and_is_truncated(db) -> None:  # noqa: ANN001
    a = auth.upsert_user(db, auth.GoogleProfile("s1", "alice@example.com", "  "))
    b = auth.upsert_user(db, auth.GoogleProfile("s2", "b@example.com", "가" * 100))
    assert a.nickname == "alice"
    assert b.nickname == "가" * 64


# ---------- 구글과 통신 (httpx 가짜 서버) ----------
def use_google(monkeypatch, handler) -> None:  # noqa: ANN001
    original = auth._client
    monkeypatch.setattr(
        auth, "_client", lambda s: original(s, transport=httpx.MockTransport(handler))
    )


def google_ok(info: dict):  # noqa: ANN201
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == auth.GOOGLE_TOKEN_URL:
            body = request.content.decode()
            assert "code_verifier=verifier-1" in body and "code=the-code" in body
            return httpx.Response(200, json={"access_token": "tok", "token_type": "Bearer"})
        assert str(request.url) == auth.GOOGLE_USERINFO_URL
        assert request.headers["authorization"] == "Bearer tok"
        return httpx.Response(200, json=info)

    return handler


def test_fetch_google_profile_ok(monkeypatch) -> None:  # noqa: ANN001
    info = {"sub": "123", "email": "a@example.com", "email_verified": True, "name": "A"}
    use_google(monkeypatch, google_ok(info))
    p = auth.fetch_google_profile("the-code", "verifier-1", settings())
    assert p == auth.GoogleProfile(sub="123", email="a@example.com", name="A")


@pytest.mark.parametrize(
    "info",
    [
        {"sub": "1", "email": "a@example.com", "email_verified": False},
        {"sub": "1", "email": "a@example.com"},
        {"email": "a@example.com", "email_verified": True},
        {"sub": "1", "email_verified": True},
    ],
)
def test_fetch_google_profile_requires_sub_and_verified_email(monkeypatch, info) -> None:  # noqa: ANN001
    use_google(monkeypatch, google_ok(info))
    with pytest.raises(ApiError) as exc:
        auth.fetch_google_profile("the-code", "verifier-1", settings())
    assert code_error(exc) == "LOGIN_FAILED"


def test_fetch_google_profile_token_rejected(monkeypatch) -> None:  # noqa: ANN001
    use_google(
        monkeypatch,
        lambda request: httpx.Response(400, json={"error": "invalid_grant"}),
    )
    with pytest.raises(ApiError) as exc:
        auth.fetch_google_profile("bad", "v", settings())
    assert code_error(exc) == "LOGIN_FAILED"


def test_fetch_google_profile_google_unreachable(monkeypatch) -> None:  # noqa: ANN001
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    use_google(monkeypatch, down)
    with pytest.raises(ApiError) as exc:
        auth.fetch_google_profile("c", "v", settings())
    assert exc.value.status_code == 503


# ---------- 세션 ----------
def test_session_lifecycle(valkey) -> None:  # noqa: ANN001
    sid = auth.create_session(7)
    assert valkey.data[session_key(sid)] == "7"
    assert len(sid) >= 40 and auth.create_session(7) != sid  # 추측할 수 없는 값, 매번 다름
    valkey.ttl[session_key(sid)] = 5
    assert auth.refresh_session(sid) is True
    assert valkey.ttl[session_key(sid)] == SESSION_TTL_SECONDS
    auth.delete_session(sid)
    assert session_key(sid) not in valkey.data
    assert auth.refresh_session(sid) is False
    auth.delete_session(sid)  # 이미 없어도 오류 없음


def test_cookie_options_are_safe() -> None:
    for opts in (auth.session_cookie_options(), auth.state_cookie_options()):
        assert opts["httponly"] is True and opts["secure"] is True and opts["samesite"] == "lax"
    assert auth.state_cookie_options()["path"] == "/api/auth"
    assert auth.session_cookie_options()["max_age"] == SESSION_TTL_SECONDS
