"""게임 라우터: 사양(#29) 등. 로그인 없이 볼 수 있다. 읽기 전용(Replica, 실패 시 Primary 폴백).

`/games/{game_id}` 같은 경로 변수 라우트는 `/games/popular`처럼 고정 경로보다 **뒤에** 둔다.
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_read_db
from app.schemas.profile import RequirementsOut
from app.services import requirements

router = APIRouter(prefix="/api")

Db = Annotated[Session, Depends(get_read_db)]


@router.get("/games/{game_id}/requirements", response_model=RequirementsOut)
def game_requirements(game_id: int, db: Db) -> RequirementsOut:
    return requirements.get_requirements(db, game_id)
