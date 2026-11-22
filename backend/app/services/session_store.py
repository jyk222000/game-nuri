"""Valkey 세션 조회. 세션 생성·삭제(로그인·로그아웃)는 로그인 구현(auth.py)이 맡는다.

인터페이스: 키 `session:{id}`, 값은 user_id 숫자 문자열, TTL은 core.keys.SESSION_TTL_SECONDS.
세션 id·토큰은 로그에 남기지 않는다.
"""

import logging

import redis

from app.clients.valkey import get_valkey
from app.core.errors import unavailable
from app.core.keys import session_key

log = logging.getLogger(__name__)
MAX_SESSION_ID_LEN = 128


def get_user_id(session_id: str) -> int | None:
    """세션이 유효하면 user_id, 없거나 형식이 틀리면 None. Valkey가 안 되면 503."""
    if not session_id or len(session_id) > MAX_SESSION_ID_LEN:
        return None
    try:
        value = get_valkey().get(session_key(session_id))
    except redis.RedisError as exc:
        log.warning("session store down: %s", type(exc).__name__)
        raise unavailable() from exc
    if value is None or not str(value).isdigit():
        return None
    return int(value)
