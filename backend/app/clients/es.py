"""Elasticsearch 클라이언트. ES가 아직 없어도 앱이 뜨도록 생성만 하고 연결은 호출 때 한다.

elk의 ES는 로그인이 켜져 있다. `ES_USER`·`ES_PASSWORD`가 있으면 기본 인증으로 접속하고,
둘 다 비어 있으면 계정 없이 접속한다(로컬·인증 없는 ES). 비밀번호는 로그에 남기지 않는다.
"""

from functools import lru_cache

from elasticsearch import Elasticsearch
from gamenuri_common.config import Settings, get_settings


def es_auth(settings: Settings) -> tuple[str, str] | None:
    """(user, password) 또는 계정 없음(None). 사용자 이름이 있을 때만 인증한다."""
    if settings.es_user:
        return settings.es_user, settings.es_password
    return None


@lru_cache
def get_es() -> Elasticsearch:
    settings = get_settings()
    return Elasticsearch(
        settings.es_url,
        basic_auth=es_auth(settings),
        request_timeout=2,
        max_retries=0,
    )
