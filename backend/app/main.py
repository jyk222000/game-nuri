from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator

from app.api import health

app = FastAPI(title="겜누리 API")
app.include_router(health.router)

# /metrics — Prometheus가 수집한다 (⑩ API 순위).
Instrumentator().instrument(app).expose(app, include_in_schema=False)
