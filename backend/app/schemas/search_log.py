"""실시간 검색어(#34)·최근 검색어(#35) 응답 모양 (docs/contracts/api.md '검색' 절)."""

from typing import Literal

from pydantic import BaseModel


class TrendingItem(BaseModel):
    rank: int
    query: str
    count: int
    change: Literal["up", "down", "same", "new"]  # 바로 앞 구간과 비교한 순위 변화


class TrendingOut(BaseModel):
    window: str  # 집계 구간. 지금은 항상 "1h"
    items: list[TrendingItem]


class RecentOut(BaseModel):
    items: list[str]
