from typing import Literal

from pydantic import BaseModel


class ApiRankingItem(BaseModel):
    rank: int
    api: str  # "GET /api/games"
    calls: int


class ApiRankingOut(BaseModel):
    items: list[ApiRankingItem]
    status: Literal["ok", "degraded"] = "ok"
