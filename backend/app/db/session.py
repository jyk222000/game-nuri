"""MariaDB 연결 두 개. 쓰기 = Primary(MARIADB_HOST), 읽기 = Replica(MARIADB_READ_HOST).

- 일반 조회 API는 읽기 연결(get_read_db).
- 사용자 본인 데이터(찜·알림 직후 조회)는 복제 지연 때문에 쓰기 연결로 읽는다(get_write_db).
- 계정명·비밀번호는 환경 변수(MARIADB_USER, MARIADB_PASSWORD)에서만 읽는다.
"""

import logging
from collections.abc import Iterator
from functools import lru_cache

from gamenuri_common.config import get_settings
from sqlalchemy import URL, Engine, create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

log = logging.getLogger(__name__)


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
        connect_args={"connect_timeout": 2},
    )


@lru_cache
def get_write_engine() -> Engine:
    return _make_engine(get_settings().mariadb_host)


@lru_cache
def get_read_engine() -> Engine:
    return _make_engine(get_settings().mariadb_read_host)


def get_read_db() -> Iterator[Session]:
    """일반 조회용. Replica 연결이 실패하면 Primary로 읽는다(사이트 전체가 멈추지 않게)."""
    session = sessionmaker(bind=get_read_engine(), expire_on_commit=False)()
    try:
        session.connection()  # 여기서 실제 연결을 맺어 본다 (timeout 2초)
    except SQLAlchemyError as exc:
        log.warning("replica 연결 실패, primary로 읽음: %s", type(exc).__name__)
        session.close()
        session = sessionmaker(bind=get_write_engine(), expire_on_commit=False)()
    try:
        yield session
    finally:
        session.close()


def get_write_db() -> Iterator[Session]:
    with sessionmaker(bind=get_write_engine(), expire_on_commit=False)() as session:
        yield session
