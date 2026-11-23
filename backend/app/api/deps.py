"""공용 의존성. 로그인이 필요한 API는 `Depends(get_current_user)`를 쓴다 (api.md의 ✓)."""

from dataclasses import dataclass

from fastapi import Request

from app.core.config import get_backend_settings
from app.core.errors import ApiError, unauthorized
from app.core.keys import SESSION_COOKIE_NAME
from app.services import session_store


@dataclass(frozen=True)
class CurrentUser:
    user_id: int
    is_fake: bool = False


def get_current_user(request: Request) -> CurrentUser:
    """세션 쿠키 → Valkey 세션 → user_id. 이메일·토큰은 다루지 않는다.

    - 쿠키가 있으면 세션만 믿는다. 없거나 만료된 세션이면 401.
    - 쿠키가 없고 AUTH_FAKE_USER가 켜져 있을 때만 가짜 사용자(개발용).
    """
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if session_id:
        user_id = session_store.get_user_id(session_id)
        if user_id is None:
            raise unauthorized()
        return CurrentUser(user_id=user_id)

    settings = get_backend_settings()
    if settings.auth_fake_user:
        return CurrentUser(user_id=settings.auth_fake_user_id, is_fake=True)
    raise unauthorized()


def get_optional_user_id(request: Request) -> int | None:
    """로그인했으면 user_id, 아니면 None. 로그인 없이도 쓰는 API(클릭스트림 등)용.

    세션이 잘못됐거나 Valkey가 안 돼도 오류를 내지 않고 익명으로 본다(fail-open).
    """
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if not session_id:
        return None
    try:
        return session_store.get_user_id(session_id)
    except ApiError:  # Valkey 장애(503): 익명으로 처리
        return None
