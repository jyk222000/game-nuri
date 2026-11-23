"""운영 통계 라우터. 로그인 없이 본다."""

from typing import Annotated

from fastapi import APIRouter, Query

from app.schemas.stats import ApiRankingOut
from app.services import api_ranking

router = APIRouter(prefix="/api/stats")


@router.get("/api-ranking", response_model=ApiRankingOut)
def api_ranking_list(size: Annotated[int, Query(ge=1, le=50)] = 10) -> ApiRankingOut:
    return api_ranking.get_ranking(size)
