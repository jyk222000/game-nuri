"""리뷰 목록(#26)·리뷰 요약(#27). 로그인 없이 본다. 얇게 두고 일은 services/reviews.py가 한다."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_read_db
from app.schemas.reviews import ReviewsOut, ReviewSummaryOut
from app.services import reviews

router = APIRouter(prefix="/api")

Db = Annotated[Session, Depends(get_read_db)]


@router.get("/games/{game_id}/reviews", response_model=ReviewsOut)
def game_reviews(
    game_id: int,
    db: Db,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=50)] = 10,
    sort: Literal["helpful", "recent"] = "helpful",
) -> ReviewsOut:
    return reviews.list_reviews(db, game_id, page, size, sort)


@router.get("/games/{game_id}/reviews/summary", response_model=ReviewSummaryOut)
def game_review_summary(game_id: int, db: Db) -> ReviewSummaryOut:
    return reviews.get_summary(db, game_id)
