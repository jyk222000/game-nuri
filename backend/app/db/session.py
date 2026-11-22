"""MariaDB 연결 두 개. 쓰기 = Primary(MARIADB_HOST), 읽기 = Replica(MARIADB_READ_HOST).

- 일반 조회 API는 읽기 연결(get_read_db).
- 사용자 본인 데이터(찜·알림 직후 조회)는 복제 지연 때문에 쓰기 연결로 읽는다(get_write_db).
- 계정명·비밀번호는 환경 변수(MARIADB_USER, MARIADB_PASSWORD)에서만 읽는다.
"""

from collections.abc import Iterator
from functools import lru_cache

from gamenuri_common.config import get_settings
from sqlalchemy import URL, Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker


def _build_url(host: str) -> URL:
    s = get_settings()
    return URL.create(
        "mysql+pymysql",
        username=s.mariadb_user,
        password=s.mariadb_password,
        host=host,
        port=s.mariadb_port,
        database=s.mariadb_db,
        query={"charset": "utf8mb4"},
    )


def _make_engine(host: str) -> Engine:
    # 연결은 처음 쓸 때 맺는다. DB가 꺼져 있어도 앱은 뜬다.
    return create_engine(
        _build_url(host),
        pool_pre_ping=True,
        pool_recycle=1800,
        connect_args={"connect_timeout": 3},
    )


@lru_cache
def get_write_engine() -> Engine:
    return _make_engine(get_settings().mariadb_host)


@lru_cache
def get_read_engine() -> Engine:
    return _make_engine(get_settings().mariadb_read_host)


def get_read_db() -> Iterator[Session]:
    with sessionmaker(bind=get_read_engine(), expire_on_commit=False)() as session:
        yield session


def get_write_db() -> Iterator[Session]:
    with sessionmaker(bind=get_write_engine(), expire_on_commit=False)() as session:
        yield session
