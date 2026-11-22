"""Elasticsearch 클라이언트. ES가 아직 없어도 앱이 뜨도록 생성만 하고 연결은 호출 때 한다."""

from functools import lru_cache

from elasticsearch import Elasticsearch
from gamenuri_common.config import get_settings


@lru_cache
def get_es() -> Elasticsearch:
    return Elasticsearch(get_settings().es_url, request_timeout=2, max_retries=0)
