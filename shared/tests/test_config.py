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


def test_google_login_settings_default_to_empty() -> None:
    s = Settings(_env_file=None)
    assert (s.google_client_id, s.google_client_secret) == ("", "")
    assert (s.google_redirect_uri, s.session_secret) == ("", "")


def test_google_login_settings_come_from_environment(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "dummy-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "dummy-secret")
    monkeypatch.setenv("GOOGLE_REDIRECT_URI", "https://example.test/api/auth/google/callback")
    monkeypatch.setenv("SESSION_SECRET", "dummy-session")
    s = Settings(_env_file=None)
    assert s.google_client_id == "dummy-id"
    assert s.google_redirect_uri.endswith("/api/auth/google/callback")
    assert s.session_secret == "dummy-session"
