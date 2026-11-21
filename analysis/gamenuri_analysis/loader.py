from __future__ import annotations

from .dataset import Dataset


def load_dataset(source: str = "mock") -> Dataset:
    """분석 데이터를 읽는다. source="mock"(가설을 담은 가짜 데이터) | "db"(MariaDB Replica)."""
    if source == "mock":
        from .mock_data import build_mock

        return build_mock()
    if source == "db":
        # 데이터 규칙: MariaDB Replica(MARIADB_READ_HOST)에서 읽기 전용 계정으로만 읽는다.
        # 정제 테이블 이름·컬럼이 erd.sql 로 확정되면 여기서 SELECT 해 Dataset 을 채운다.
        raise NotImplementedError(
            "DB 로더는 정제 테이블이 채워진 뒤 구현한다 (Dataset docstring 참고)"
        )
    raise ValueError(f"알 수 없는 source: {source}")
