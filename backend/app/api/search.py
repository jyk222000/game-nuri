"""실시간 검색어(#34)·최근 검색어(#35). 얇게 유지하고 일은 services/search_log.py가 한다."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import CurrentUser, get_current_user
from app.schemas.search_log import RecentOut, TrendingOut
from app.services import search_log

router = APIRouter(prefix="/api/search")

User = Annotated[CurrentUser, Depends(get_current_user)]


@router.get("/trending", response_model=TrendingOut)
def trending() -> TrendingOut:
    return search_log.get_trending()


@router.get("/recent", response_model=RecentOut)
def recent(user: User) -> RecentOut:
    return search_log.get_recent(user.user_id)
