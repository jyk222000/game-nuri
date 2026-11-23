"""구매 타이밍(#15)·할인 예측(#16) 라우터. 로그인 없이 볼 수 있다. 읽기 전용."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_read_db
from app.schemas.timing import TimingOut
from app.services import timing

router = APIRouter(prefix="/api")

Db = Annotated[Session, Depends(get_read_db)]


@router.get("/games/{game_id}/timing", response_model=TimingOut)
def game_timing(game_id: int, db: Db) -> TimingOut:
    return timing.get_timing(db, game_id)
