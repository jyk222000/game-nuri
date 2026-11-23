"""게임 최소·권장 사양(#29). game_requirements는 읽기만 한다 (텍스트 컬럼 그대로)."""

from sqlalchemy.orm import Session

from app.db.models import GameRequirement
from app.schemas.profile import RequirementsOut
from app.services import games


def get_requirements(db: Session, game_id: int) -> RequirementsOut:
    games.ensure_exists(db, game_id)
    row = db.get(GameRequirement, game_id)
    if row is None:  # 사양 정보가 아직 없는 게임
        return RequirementsOut(
            game_id=game_id, minimum_text=None, recommended_text=None, updated_at=None
        )
    return RequirementsOut(
        game_id=game_id,
        minimum_text=row.minimum_text,
        recommended_text=row.recommended_text,
        updated_at=row.updated_at,
    )
