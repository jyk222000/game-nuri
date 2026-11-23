"""가격 라우터(#10~14). 로그인 없이 볼 수 있다. 읽기 전용(Replica, 실패 시 Primary 폴백)."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_read_db
from app.schemas.price import PricesOut
from app.services import prices

router = APIRouter(prefix="/api")

Db = Annotated[Session, Depends(get_read_db)]


@router.get("/games/{game_id}/prices", response_model=PricesOut)
def game_prices(game_id: int, db: Db) -> PricesOut:
    return prices.get_prices(db, game_id)
