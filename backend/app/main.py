import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator

from app.api import (
    auth,
    events,
    games,
    health,
    me,
    prices,
    profile,
    reviews,
    search,
    stats,
    timing,
)
from app.clients import kafka
from app.core.config import get_backend_settings
from app.core.errors import register_error_handlers

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    if get_backend_settings().auth_fake_user:
        log.warning(
            "AUTH_FAKE_USER가 켜져 있습니다. 로그인 없이 가짜 사용자로 동작합니다 (개발용)."
        )
    yield
    kafka.close()  # 아직 안 나간 clickstream 메시지를 보낸다


app = FastAPI(title="겜누리 API", lifespan=lifespan)
register_error_handlers(app)
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(me.router)
app.include_router(profile.router)
app.include_router(prices.router)
app.include_router(timing.router)
app.include_router(games.router)
app.include_router(reviews.router)
app.include_router(events.router)
app.include_router(search.router)
app.include_router(stats.router)

# /metrics — Prometheus가 수집한다 (⑩ API 순위).
Instrumentator().instrument(app).expose(app, include_in_schema=False)
