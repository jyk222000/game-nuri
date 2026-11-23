"""가격 라우터(#10~14). 로그인 없이 볼 수 있다. 읽기 전용(Replica, 실패 시 Primary 폴백)."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_read_db
from app.schemas.price import DealsOut, HistoryOut, LowestOut, PricesOut
from app.services import deals, history, lowest, prices

router = APIRouter(prefix="/api")

Db = Annotated[Session, Depends(get_read_db)]


@router.get("/games/{game_id}/prices", response_model=PricesOut)
def game_prices(game_id: int, db: Db) -> PricesOut:
    return prices.get_prices(db, game_id)


@router.get("/games/{game_id}/history", response_model=HistoryOut)
def game_history(
    game_id: int,
    db: Db,
    days: Annotated[int, Query(ge=1, le=3650)] = 180,
    platform: Annotated[str | None, Query(max_length=16)] = None,
    item_condition: Literal["new", "used"] | None = None,
) -> HistoryOut:
    return history.get_history(db, game_id, days, platform, item_condition)


@router.get("/games/{game_id}/lowest", response_model=LowestOut)
def game_lowest(game_id: int, db: Db) -> LowestOut:
    return lowest.get_lowest(db, game_id)


@router.get("/games/deals", response_model=DealsOut)
def game_deals(db: Db, size: Annotated[int, Query(ge=1, le=100)] = 20) -> DealsOut:
    return DealsOut(items=deals.get_deals(db, size))
