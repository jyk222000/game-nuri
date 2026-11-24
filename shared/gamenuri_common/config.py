"""환경 변수는 이 Settings로만 읽는다. 새 값이 필요하면 여기와 .env.example에 함께 추가한다."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: str = "local"
    log_level: str = "INFO"
    server_name: str = ""

    kafka_bootstrap: str = "localhost:9092"
    kafka_connect_url: str = "http://localhost:8083"

    mariadb_host: str = "localhost"
    mariadb_read_host: str = "localhost"
    mariadb_port: int = 3306
    mariadb_db: str = "gamenuri"
    mariadb_user: str = ""
    mariadb_password: str = ""

    mongo_uri: str = "mongodb://localhost:27017"
    mongo_db: str = "gamenuri_raw"
    es_url: str = "http://localhost:9200"
    es_user: str = ""  # ES 로그인이 켜져 있으면 설정 (elk의 ES는 켜짐). 비어 있으면 계정 없이 접속
    es_password: str = ""
    valkey_url: str = "redis://localhost:6379/0"

    itad_key: str = ""
    twitch_client_id: str = ""
    twitch_client_secret: str = ""
    steam_key: str = ""
    gemini_api_key: str = ""
    ai_model: str = ""

    # 구글 로그인 (Backend). Backend 2대가 같은 session_secret을 써야 state 확인이 서로 통한다.
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = ""  # 구글 콘솔에 등록한 값과 한 글자도 다르면 안 된다
    session_secret: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
