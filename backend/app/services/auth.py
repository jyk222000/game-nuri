"""구글 로그인(#1)·세션 갱신·로그아웃(#2). 라우터(api/auth.py)는 이 모듈을 불러 쓰기만 한다.

흐름
1. `start_login()`   → 구글 로그인 주소와 "state 쿠키" 값을 만든다
                      (라우터가 리다이렉트하고 쿠키를 설정한다).
2. (사용자가 구글에서 로그인하면 구글이 콜백 주소로 `code`와 `state`를 붙여 돌려보낸다)
3. `finish_login()`  → state 쿠키로 우리가 시작한 요청인지 확인하고, 구글에서 사용자 정보를
                      받아 users에 만들거나 찾은 뒤 Valkey에 세션을 만든다.
4. 라우터가 세션 id를 세션 쿠키로 내려 준다. 이후 요청은 `deps.get_current_user`가 처리한다.

설계
- Backend가 2대라 state를 서버 메모리나 Starlette 세션에 두지 않는다. `SESSION_SECRET`으로
  서명한 짧은 쿠키(10분)에 담아서, 로그인 시작과 콜백이 서로 다른 서버로 가도 확인된다
  (두 서버의 값이 같아야 한다).
- PKCE(S256)를 쓴다. 인증 코드가 가로채여도 code_verifier(쿠키 안)가 없으면 교환되지 않는다.
- 사용자 정보는 구글 토큰 엔드포인트에서 직접 받은 access_token으로 userinfo를 조회한다
  (TLS 직접 통신).
- 이메일·구글 계정 ID(sub)·토큰·인증 코드는 로그에 남기지 않는다.
"""

import hmac
import logging
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime

import redis
from authlib.integrations.base_client.errors import OAuthError
from authlib.integrations.httpx_client import OAuth2Client
from httpx import HTTPError
from itsdangerous import BadSignature, URLSafeTimedSerializer
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.clients.valkey import get_valkey
from app.core.config import BackendSettings, get_backend_settings
from app.core.errors import ApiError, unavailable
from app.core.keys import SESSION_TTL_SECONDS, session_key
from app.db.models import User

log = logging.getLogger(__name__)

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
GOOGLE_SCOPE = "openid email profile"

STATE_COOKIE_NAME = "gamenuri_oauth"  # 로그인 중에만 쓰는 임시 쿠키
STATE_MAX_AGE_SECONDS = 10 * 60
HTTP_TIMEOUT_SECONDS = 5
NICKNAME_MAX_LEN = 64  # users.nickname VARCHAR(64)


@dataclass(frozen=True)
class LoginStart:
    url: str  # 사용자를 보낼 구글 로그인 주소
    state_cookie: str  # STATE_COOKIE_NAME 쿠키에 넣을 값


@dataclass(frozen=True)
class LoginResult:
    session_id: str  # 세션 쿠키에 넣을 값 (로그에 남기지 않는다)
    user_id: int


@dataclass(frozen=True)
class GoogleProfile:
    sub: str  # 구글 계정 고유 ID
    email: str
    name: str


def login_failed() -> ApiError:
    return ApiError(400, "LOGIN_FAILED", "로그인에 실패했어요. 처음부터 다시 시도해 주세요")


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)  # DB는 UTC naive


def _settings(settings: BackendSettings | None) -> BackendSettings:
    return settings or get_backend_settings()


def _require_configured(s: BackendSettings) -> None:
    """구글 키·세션 비밀값이 비어 있으면 로그인을 시작하지 않는다(설정 누락)."""
    if not (s.google_client_id and s.google_client_secret and s.google_redirect_uri):
        log.error("구글 로그인 설정(GOOGLE_*)이 비어 있습니다")
        raise unavailable("구글 로그인이 아직 준비되지 않았어요")
    if not s.session_secret:
        log.error("SESSION_SECRET이 비어 있습니다")
        raise unavailable("구글 로그인이 아직 준비되지 않았어요")


def _serializer(s: BackendSettings) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(s.session_secret, salt="gamenuri-oauth-state")


def _client(s: BackendSettings, **kwargs: object) -> OAuth2Client:
    return OAuth2Client(
        client_id=s.google_client_id,
        client_secret=s.google_client_secret,
        redirect_uri=s.google_redirect_uri,
        scope=GOOGLE_SCOPE,
        code_challenge_method="S256",
        timeout=HTTP_TIMEOUT_SECONDS,
        **kwargs,
    )


# ---------- 쿠키 속성 (라우터가 그대로 set_cookie(**옵션)에 쓴다) ----------
def session_cookie_options() -> dict[str, object]:
    # Secure: 사용자는 HTTPS(HAProxy)로 접속한다. Lax: 구글에서 돌아오는 이동에는 쿠키가 같이 간다.
    return {
        "httponly": True,
        "secure": True,
        "samesite": "lax",
        "max_age": SESSION_TTL_SECONDS,
        "path": "/",
    }


def state_cookie_options() -> dict[str, object]:
    return {
        "httponly": True,
        "secure": True,
        "samesite": "lax",
        "max_age": STATE_MAX_AGE_SECONDS,
        "path": "/api/auth",
    }


# ---------- 1. 로그인 시작 ----------
def start_login(settings: BackendSettings | None = None) -> LoginStart:
    s = _settings(settings)
    _require_configured(s)
    verifier = secrets.token_urlsafe(48)
    url, state = _client(s).create_authorization_url(
        GOOGLE_AUTH_URL, code_verifier=verifier, prompt="select_account"
    )
    return LoginStart(
        url=url, state_cookie=_serializer(s).dumps({"state": state, "verifier": verifier})
    )


# ---------- 2. 구글에서 돌아온 뒤 ----------
def fetch_google_profile(
    code: str, code_verifier: str, settings: BackendSettings | None = None
) -> GoogleProfile:
    """인증 코드를 토큰으로 바꾸고 구글 사용자 정보를 받는다. 실패는 ApiError로 바꿔 던진다."""
    s = _settings(settings)
    try:
        with _client(s) as client:
            client.fetch_token(GOOGLE_TOKEN_URL, code=code, code_verifier=code_verifier)
            info = client.get(GOOGLE_USERINFO_URL).json()
    except OAuthError as exc:
        log.warning("구글 토큰 교환 거절: %s", exc.error)  # 오류 종류만 (코드·토큰은 남기지 않는다)
        raise login_failed() from None
    except (HTTPError, ValueError) as exc:
        log.warning("구글 통신 실패: %s", type(exc).__name__)
        raise unavailable("구글과 통신하지 못했어요. 잠시 후 다시 시도해 주세요") from None

    sub, email = info.get("sub"), info.get("email")
    if not sub or not email or info.get("email_verified") is not True:
        log.warning("구글 사용자 정보에 sub·확인된 이메일이 없습니다")
        raise login_failed()
    return GoogleProfile(sub=str(sub), email=str(email), name=str(info.get("name") or ""))


def _check_state(s: BackendSettings, state: str | None, state_cookie: str | None) -> str:
    """state 쿠키를 검증하고 code_verifier를 돌려준다. 하나라도 어긋나면 로그인 실패."""
    if not state or not state_cookie:
        raise login_failed()
    try:
        data = _serializer(s).loads(state_cookie, max_age=STATE_MAX_AGE_SECONDS)
    except BadSignature:  # 서명 불일치·만료
        raise login_failed() from None
    saved, verifier = data.get("state"), data.get("verifier")
    if not saved or not verifier or not hmac.compare_digest(str(saved), state):
        raise login_failed()
    return str(verifier)


def upsert_user(db: Session, profile: GoogleProfile) -> User:
    """구글 계정(sub)으로 사용자를 찾는다.

    없으면 같은 이메일의 기존 계정에 연결하고, 그래도 없으면 새로 만든다.

    이미 있는 사용자의 닉네임은 건드리지 않는다(사용자가 바꿨을 수 있다).
    """
    user = db.scalar(select(User).where(User.google_sub == profile.sub))
    if user is not None:
        return user
    user = db.scalar(select(User).where(User.email == profile.email))
    if user is not None:
        user.google_sub = profile.sub  # 이메일 확인이 끝난 구글 계정이라 연결해도 안전하다
        db.commit()
        return user
    nickname = (profile.name.strip() or profile.email.split("@")[0])[:NICKNAME_MAX_LEN]
    user = User(email=profile.email, google_sub=profile.sub, nickname=nickname, created_at=_now())
    db.add(user)
    try:
        db.commit()
    except IntegrityError:  # 같은 사람이 동시에 두 번 로그인한 경우: 먼저 만들어진 것을 쓴다
        db.rollback()
        existing = db.scalar(select(User).where(User.google_sub == profile.sub))
        if existing is None:
            raise
        return existing
    return user


def finish_login(
    db: Session,
    code: str | None,
    state: str | None,
    state_cookie: str | None,
    settings: BackendSettings | None = None,
) -> LoginResult:
    s = _settings(settings)
    _require_configured(s)
    if not code:  # 사용자가 구글 화면에서 '취소'하면 code 없이 돌아온다
        raise login_failed()
    verifier = _check_state(s, state, state_cookie)
    profile = fetch_google_profile(code, verifier, s)
    user = upsert_user(db, profile)
    session_id = create_session(user.user_id)
    log.info("로그인 user_id=%s", user.user_id)
    return LoginResult(session_id=session_id, user_id=user.user_id)


# ---------- 3. 세션 (Valkey: session:{id} = user_id) ----------
def create_session(user_id: int) -> str:
    session_id = secrets.token_urlsafe(32)
    try:
        get_valkey().set(session_key(session_id), str(user_id), ex=SESSION_TTL_SECONDS)
    except redis.RedisError as exc:
        log.warning("세션 저장 실패: %s", type(exc).__name__)
        raise unavailable() from exc
    return session_id


def refresh_session(session_id: str) -> bool:
    """세션 유효 기간을 처음부터 다시 센다. 세션이 없으면 False."""
    try:
        return bool(get_valkey().expire(session_key(session_id), SESSION_TTL_SECONDS))
    except redis.RedisError as exc:
        log.warning("세션 갱신 실패: %s", type(exc).__name__)
        raise unavailable() from exc


def delete_session(session_id: str) -> None:
    """로그아웃. 세션이 이미 없어도 오류가 아니다."""
    try:
        get_valkey().delete(session_key(session_id))
    except redis.RedisError as exc:
        log.warning("세션 삭제 실패: %s", type(exc).__name__)
        raise unavailable() from exc
