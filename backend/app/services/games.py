"""게임 존재 확인 (읽기 전용 테이블 조회)."""

from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.db.models import Game


def ensure_exists(db: Session, game_id: int) -> Game:
    """없으면 404 NOT_FOUND. wishlists·alerts에는 games FK가 없어서 코드에서 확인한다."""
    game = db.get(Game, game_id)
    if game is None:
        raise ApiError(404, "NOT_FOUND", "게임을 찾을 수 없습니다")
    return game
