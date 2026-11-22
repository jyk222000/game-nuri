"""GET /api/health — DB(읽기·쓰기)가 안 되면 503, Valkey·ES만 안 되면 200 + degraded."""

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from gamenuri_common.config import get_settings

from app.services import health as checks

router = APIRouter()


@router.get("/api/health")
def health() -> JSONResponse:
    db_write = checks.check_db_write()
    db_read = checks.check_db_read()
    valkey = checks.check_valkey()
    es = checks.check_es()

    if db_write != "ok" or db_read != "ok":
        status, code = "down", 503
    elif valkey != "ok" or es != "ok":
        status, code = "degraded", 200
    else:
        status, code = "ok", 200

    body = {
        "status": status,
        "server": getattr(get_settings(), "server_name", ""),
        "db_write": db_write,
        "db_read": db_read,
        "valkey": valkey,
        "es": es,
    }
    return JSONResponse(body, status_code=code)
