"""리뷰 목록(#26)·리뷰 요약(#27) 응답 모양 (docs/contracts/api.md '리뷰' 절)."""

from typing import Literal

from pydantic import BaseModel

from app.core.timeutil import UtcDatetime


class ReviewItem(BaseModel):
    review_id: str  # Steam recommendationid
    source: str  # 지금은 steam뿐
    recommended: bool  # voted_up
    text: str  # 리뷰 원문 전체(길이 제한 없음, Steam BBCode 포함)
    playtime_hours: int | None  # 리뷰를 쓸 때까지의 플레이 시간(시간, 반올림)
    created_at: UtcDatetime


class ReviewsOut(BaseModel):
    items: list[ReviewItem]
    total: int
    page: int
    size: int


class ReviewSummaryOut(BaseModel):
    """요약이 아직 없는 게임도 200이다: 값이 없는 필드는 null·빈 목록."""

    game_id: int
    positive_ratio: float | None  # 0~1. 카드의 긍정률과 같은 값
    summary: str | None
    pros: list[str]
    cons: list[str]
    generated_by: Literal["ai", "fallback"] | None  # 요약이 없으면 null
    updated_at: UtcDatetime | None
