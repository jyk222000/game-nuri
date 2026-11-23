"""메일 수신 설정 (#22). 행이 없으면 기본값 true로 본다 (erd.sql DEFAULT TRUE)."""

from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import NotificationSetting


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def get_email_enabled(db: Session, user_id: int) -> bool:
    row = db.get(NotificationSetting, user_id)
    return True if row is None else bool(row.email_enabled)


def set_email_enabled(db: Session, user_id: int, enabled: bool) -> bool:
    row = db.get(NotificationSetting, user_id)
    if row is None:
        db.add(NotificationSetting(user_id=user_id, email_enabled=enabled, updated_at=_now()))
    else:
        row.email_enabled = enabled
        row.updated_at = _now()
    try:
        db.commit()
    except IntegrityError:  # 동시에 처음 저장한 경우
        db.rollback()
        row = db.get(NotificationSetting, user_id)
        if row is None:
            raise
        row.email_enabled = enabled
        row.updated_at = _now()
        db.commit()
    return enabled
