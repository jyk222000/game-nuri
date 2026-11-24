"""ES 접속 계정: 사용자 이름이 있을 때만 기본 인증을 쓴다."""

from app.clients.es import es_auth
from gamenuri_common.config import Settings


def _settings(**kw: str) -> Settings:
    return Settings(_env_file=None, **kw)


def test_no_credentials_means_no_auth() -> None:
    assert es_auth(_settings()) is None


def test_user_and_password_enable_basic_auth() -> None:
    assert es_auth(_settings(es_user="elastic", es_password="dummy")) == ("elastic", "dummy")


def test_password_without_user_is_ignored() -> None:
    assert es_auth(_settings(es_password="dummy")) is None
