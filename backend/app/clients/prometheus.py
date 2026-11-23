"""Prometheus HTTP API 조회 클라이언트 (API 사용 순위 #37용).

주소는 PROMETHEUS_URL 환경 변수에서만 읽는다. 사용자 요청을 오래 붙잡지 않도록 시간 제한은 2초.
"""

import httpx

from app.core.config import get_backend_settings

TIMEOUT_SECONDS = 2.0


class PrometheusError(Exception):
    """주소가 없거나, 연결·응답이 정상이 아닐 때."""


def query(promql: str) -> list[dict]:
    """즉시 쿼리(/api/v1/query)의 result 목록을 돌려준다. 실패하면 PrometheusError."""
    base = get_backend_settings().prometheus_url.rstrip("/")
    if not base:
        raise PrometheusError("PROMETHEUS_URL 미설정")
    try:
        resp = httpx.get(f"{base}/api/v1/query", params={"query": promql}, timeout=TIMEOUT_SECONDS)
        resp.raise_for_status()
        body = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise PrometheusError(type(exc).__name__) from exc
    if body.get("status") != "success":
        raise PrometheusError("쿼리 실패")
    return body.get("data", {}).get("result", [])
