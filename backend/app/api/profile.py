"""내 정보 라우터: 프로필(#3), Steam ID(#4), 내 PC 사양(#30). 모두 로그인 필요, Primary 세션."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_current_user
from app.db.session import get_write_db
from app.schemas.game import RecommendationsOut
from app.schemas.me import TasteOut
from app.schemas.profile import MeOut, MePatch, SpecsBody, SpecsOut, SteamBody, SteamOut
from app.services import profile, taste

router = APIRouter(prefix="/api/me")

User = Annotated[CurrentUser, Depends(get_current_user)]
Db = Annotated[Session, Depends(get_write_db)]


def _me_out(user) -> MeOut:  # noqa: ANN001
    return MeOut(user_id=user.user_id, email=user.email, name=user.nickname, steam_id=user.steam_id)


@router.get("", response_model=MeOut)
def get_me(user: User, db: Db) -> MeOut:
    return _me_out(profile.get_user(db, user.user_id))


@router.patch("", response_model=MeOut)
def patch_me(body: MePatch, user: User, db: Db) -> MeOut:
    return _me_out(profile.rename(db, user.user_id, body.name))


@router.put("/steam", response_model=SteamOut)
def put_steam(body: SteamBody, user: User, db: Db) -> SteamOut:
    steam_id, owned = profile.set_steam_id(db, user.user_id, body.steam_id)
    return SteamOut(steam_id=steam_id, owned_games=owned)


@router.get("/specs", response_model=SpecsOut)
def get_specs(user: User, db: Db) -> SpecsOut:
    return profile.get_specs(db, user.user_id)


@router.put("/specs", response_model=SpecsOut)
def put_specs(body: SpecsBody, user: User, db: Db) -> SpecsOut:
    return profile.put_specs(db, user.user_id, body)


@router.get("/taste", response_model=TasteOut)
def get_taste(user: User, db: Db) -> TasteOut:
    return taste.get_taste(db, user.user_id)


@router.get("/recommendations", response_model=RecommendationsOut)
def get_recommendations(
    user: User, db: Db, size: Annotated[int, Query(ge=1, le=50)] = 10
) -> RecommendationsOut:
    return RecommendationsOut(items=taste.recommend(db, user.user_id, size))
