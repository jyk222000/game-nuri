"""의존 서비스 상태 점검. 각 점검은 예외를 밖으로 내보내지 않고 'ok' 또는 'down'만 돌려준다."""

import logging

from sqlalchemy import text

from app.clients.es import get_es
from app.clients.valkey import get_valkey
from app.db.session import get_read_engine, get_write_engine

log = logging.getLogger(__name__)


def check_db_write() -> str:
    return _check_db(get_write_engine, "db_write")


def check_db_read() -> str:
    return _check_db(get_read_engine, "db_read")


def _check_db(get_engine, name: str) -> str:  # noqa: ANN001
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return "ok"
    except Exception as exc:  # noqa: BLE001
        log.warning("%s down: %s", name, type(exc).__name__)
        return "down"


def check_valkey() -> str:
    try:
        return "ok" if get_valkey().ping() else "down"
    except Exception as exc:  # noqa: BLE001
        log.warning("valkey down: %s", type(exc).__name__)
        return "down"


def check_es() -> str:
    try:
        return "ok" if get_es().ping() else "down"
    except Exception as exc:  # noqa: BLE001
        log.warning("es down: %s", type(exc).__name__)
        return "down"
