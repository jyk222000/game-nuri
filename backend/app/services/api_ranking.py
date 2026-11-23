"""API 사용 순위(#37). Backend의 /metrics를 Prometheus가 모은 값을 Backend가 조회해 만든다.

- 지표: prometheus-fastapi-instrumentator의 `http_requests_total{handler, method, status}`
  (handler는 `/api/games/{game_id}`처럼 경로 틀이라 게임마다 갈라지지 않는다).
- 최근 24시간 호출 수(`increase`)를 서버 1·2를 합쳐 센다. 상태 확인·순위 API 자신은 뺀다.
- Prometheus가 안 되면 빈 목록 + status="degraded" (화면을 막지 않는다).
"""

import logging

from app.clients import prometheus
from app.schemas.stats import ApiRankingItem, ApiRankingOut

log = logging.getLogger(__name__)

WINDOW = "24h"
EXCLUDED = "/api/health|/api/stats/api-ranking"


def _promql(size: int) -> str:
    selector = f'http_requests_total{{handler=~"/api/.+", handler!~"{EXCLUDED}"}}'
    return f"topk({size}, sum by (handler, method) (increase({selector}[{WINDOW}])))"


def get_ranking(size: int) -> ApiRankingOut:
    try:
        result = prometheus.query(_promql(size))
    except prometheus.PrometheusError as exc:
        log.warning("API 순위 조회 실패(degraded): %s", exc)
        return ApiRankingOut(items=[], status="degraded")
    rows: list[tuple[str, int]] = []
    for r in result:
        try:
            calls = round(float(r["value"][1]))
            label = f"{r['metric']['method']} {r['metric']['handler']}"
        except (KeyError, IndexError, TypeError, ValueError):
            continue  # 모양이 다른 항목은 건너뛴다
        if calls > 0:
            rows.append((label, calls))
    rows.sort(key=lambda x: (-x[1], x[0]))
    items = [ApiRankingItem(rank=i, api=a, calls=c) for i, (a, c) in enumerate(rows[:size], 1)]
    return ApiRankingOut(items=items, status="ok")
