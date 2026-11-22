"""찜 추가·삭제 (#17). 둘 다 멱등이다. 쓰기는 Primary 세션으로 한다."""

from datetime import UTC, datetime

from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import Wishlist


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)  # DB는 UTC naive


def add(db: Session, user_id: int, game_id: int) -> None:
    """이미 찜했으면 아무것도 하지 않는다 (200 멱등)."""
    if db.get(Wishlist, (user_id, game_id)) is not None:
        return
    db.add(Wishlist(user_id=user_id, game_id=game_id, created_at=_now()))
    try:
        db.commit()
    except IntegrityError:  # 동시에 두 번 눌러 이미 들어간 경우
        db.rollback()


def remove(db: Session, user_id: int, game_id: int) -> None:
    """찜하지 않았어도 오류 없이 끝난다."""
    db.execute(delete(Wishlist).where(Wishlist.user_id == user_id, Wishlist.game_id == game_id))
    db.commit()
