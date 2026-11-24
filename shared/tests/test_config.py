"""Settings: ES 로그인 값은 기본이 비어 있고, 환경 변수로 읽힌다."""

from gamenuri_common.config import Settings


def test_es_credentials_default_to_empty() -> None:
    s = Settings(_env_file=None)
    assert s.es_user == ""
    assert s.es_password == ""


def test_es_credentials_come_from_environment(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setenv("ES_USER", "elastic")
    monkeypatch.setenv("ES_PASSWORD", "dummy-for-test")
    s = Settings(_env_file=None)
    assert (s.es_user, s.es_password) == ("elastic", "dummy-for-test")
