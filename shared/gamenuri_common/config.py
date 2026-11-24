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


@lru_cache
def get_settings() -> Settings:
    return Settings()
