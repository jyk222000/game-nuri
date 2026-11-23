"""게임 라우터: 검색(#5)·자동완성(#6)·상세(#7)·장르/태그(#8)·사양(#29). 로그인 없이 볼 수 있다.
읽기 전용(Replica, 실패 시 Primary 폴백).

주의: `/games/{game_id}` 같은 경로 변수 라우트는 `/games/autocomplete`처럼 고정 경로보다
**뒤에** 둔다 (먼저 두면 고정 경로가 game_id로 해석돼 422가 난다).
"""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_read_db
from app.schemas.game import (
    AutocompleteOut,
    CardsOut,
    GameDetail,
    NameListOut,
    SearchOut,
    WarningCardsOut,
)
from app.schemas.profile import RequirementsOut
from app.services import catalog, detail, rankings, requirements, search

router = APIRouter(prefix="/api")

Db = Annotated[Session, Depends(get_read_db)]


# ---- #8 장르·태그 ----
@router.get("/genres", response_model=NameListOut)
def list_genres(db: Db) -> NameListOut:
    return NameListOut(items=catalog.genre_names(db))


@router.get("/tags", response_model=NameListOut)
def list_tags(db: Db) -> NameListOut:
    return NameListOut(items=catalog.tag_names(db))


# ---- #5 검색, #6 자동완성 ----
@router.get("/games", response_model=SearchOut)
def search_games(
    db: Db,
    q: Annotated[str | None, Query(max_length=100)] = None,
    platform: Annotated[str | None, Query(max_length=16)] = None,
    genre: Annotated[str | None, Query(max_length=64)] = None,
    sort: Literal["price", "discount"] | None = None,
    page: Annotated[int, Query(ge=1, le=10000)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> SearchOut:
    items, total = search.search(db, (q or "").strip() or None, platform, genre, sort, page, size)
    return SearchOut(items=items, total=total, page=page, size=size)


@router.get("/games/autocomplete", response_model=AutocompleteOut)
def autocomplete(
    db: Db,
    q: Annotated[str, Query(min_length=1, max_length=100)],
    limit: Annotated[int, Query(ge=1, le=20)] = 10,
) -> AutocompleteOut:
    return AutocompleteOut(items=search.autocomplete(db, q.strip(), limit))


# ---- #9 인기, #25 짧게 끝낼 게임, #32·#33 동접자 ----
Size = Annotated[int, Query(ge=1, le=100)]


@router.get("/games/popular", response_model=CardsOut)
def popular_games(db: Db, size: Size = 20) -> CardsOut:
    return CardsOut(items=rankings.popular(db, size))


@router.get("/games/short", response_model=CardsOut)
def short_games(db: Db, size: Size = 20) -> CardsOut:
    return CardsOut(items=rankings.short_games(db, size))


@router.get("/games/players/top", response_model=CardsOut)
def top_players(db: Db, size: Size = 20) -> CardsOut:
    return CardsOut(items=rankings.top_players(db, size))


@router.get("/games/players/low", response_model=WarningCardsOut)
def low_players(db: Db, size: Size = 20) -> WarningCardsOut:
    return WarningCardsOut(items=rankings.low_players(db, size))


# ---- (고정 경로 라우트는 이 줄 위에 추가한다) ----


# ---- #7 상세 ----
@router.get("/games/{game_id}", response_model=GameDetail)
def game_detail(game_id: int, db: Db) -> GameDetail:
    return detail.get_detail(db, game_id)


# ---- #29 사양 ----
@router.get("/games/{game_id}/requirements", response_model=RequirementsOut)
def game_requirements(game_id: int, db: Db) -> RequirementsOut:
    return requirements.get_requirements(db, game_id)
