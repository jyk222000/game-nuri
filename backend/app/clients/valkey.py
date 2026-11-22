"""Valkey 클라이언트. 연결은 처음 쓸 때 맺는다.

비밀번호는 VALKEY_URL에 담아 환경 변수로만 받는다.
"""

from functools import lru_cache

import redis
from gamenuri_common.config import get_settings


@lru_cache
def get_valkey() -> redis.Redis:
    return redis.Redis.from_url(
        get_settings().valkey_url,
        socket_connect_timeout=1,
        socket_timeout=1,
        decode_responses=True,
    )
