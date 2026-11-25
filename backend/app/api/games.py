"""게임 라우터: 검색(#5)·자동완성(#6)·상세(#7)·장르/태그(#8)·사양(#29)·사양 판정(#31).
사양 판정(#31)만 로그인이 필요하고, 나머지는 로그인 없이 볼 수 있다.
읽기 전용(Replica, 실패 시 Primary 폴백). 사양 판정은 내 데이터(user_specs)를 읽어 Primary를 쓴다.

주의: `/games/{game_id}` 같은 경로 변수 라우트는 `/games/autocomplete`처럼 고정 경로보다
**뒤에** 둔다 (먼저 두면 고정 경로가 game_id로 해석돼 422가 난다).
"""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_current_user
from app.db.session import get_read_db, get_write_db
from app.schemas.game import (
    AutocompleteOut,
    CardsOut,
    GameDetail,
    NameListOut,
    SearchOut,
    WarningCardsOut,
)
from app.schemas.profile import RequirementsOut
from app.services import catalog, detail, rankings, requirements, search, spec_check

router = APIRouter(prefix="/api")

Db = Annotated[Session, Depends(get_read_db)]
WriteDb = Annotated[Session, Depends(get_write_db)]  # 내 데이터를 읽는 API는 Primary
User = Annotated[CurrentUser, Depends(get_current_user)]


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
    sort: Literal["price", "discount", "popular", "rating"] | None = None,
    length: Literal["short", "medium", "long"] | None = None,
    page: Annotated[int, Query(ge=1, le=10000)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> SearchOut:
    items, total = search.search(
        db, (q or "").strip() or None, platform, genre, sort, page, size, length
    )
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


# ---- #31 사양 적합도 판정 (로그인 필요, AI는 services/spec_check.py가 부른다) ----
@router.get("/games/{game_id}/spec-check", response_model=spec_check.SpecCheckOut)
def game_spec_check(game_id: int, user: User, db: WriteDb) -> spec_check.SpecCheckOut:
    return spec_check.check(db, game_id, user.user_id)
