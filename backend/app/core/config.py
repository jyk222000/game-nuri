"""Backend 전용 설정. shared의 Settings를 그대로 상속하고 Backend에만 필요한 값을 더한다.

shared는 팀 공통이라 건드리지 않는다. 환경 변수는 여전히 Settings(pydantic)로만 읽는다.
"""

from functools import lru_cache

from gamenuri_common.config import Settings


class BackendSettings(Settings):
    # 로그인 구현 전 개발용 가짜 사용자. 기본 꺼짐. 배포 .env에는 반드시 false.
    auth_fake_user: bool = False
    auth_fake_user_id: int = 1  # users 테이블에 실제로 있는 user_id여야 한다 (FK)
    # API 사용 순위(#37)용 Prometheus 주소 (예: http://monitoring:9090). 비면 degraded.
    prometheus_url: str = ""


@lru_cache
def get_backend_settings() -> BackendSettings:
    return BackendSettings()
