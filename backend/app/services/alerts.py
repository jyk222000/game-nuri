"""목표가 알림 설정·수정·삭제 (#19 POST·PATCH·DELETE).

alerts는 (user_id, game_id)가 고유라서, 이미 있으면 409가 아니라 덮어쓴다.
"""

from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.db.models import Alert, AlertLog
from app.services import games

MAX_INT = 2_147_483_647  # alerts.target_price_krw는 INT


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _check_price(price: int) -> None:
    if not 0 < price <= MAX_INT:
        raise ApiError(400, "INVALID_PRICE", "목표가를 올바르게 입력해 주세요")


def _find(db: Session, user_id: int, game_id: int) -> Alert | None:
    return db.scalars(
        select(Alert).where(Alert.user_id == user_id, Alert.game_id == game_id)
    ).first()


def upsert(db: Session, user_id: int, game_id: int, target_price_krw: int) -> Alert:
    """없으면 만들고, 있으면 목표가를 덮어쓴다(다시 켜진 상태, 만든 시각은 유지)."""
    _check_price(target_price_krw)
    games.ensure_exists(db, game_id)  # 없는 게임이면 404
    alert = _find(db, user_id, game_id)
    if alert is None:
        alert = Alert(
            user_id=user_id,
            game_id=game_id,
            target_price_krw=target_price_krw,
            active=True,
            created_at=_now(),
        )
        db.add(alert)
    else:
        alert.target_price_krw = target_price_krw
        alert.active = True
    try:
        db.commit()
    except IntegrityError:  # 동시에 두 번 만든 경우: 먼저 들어간 행을 덮어쓴다
        db.rollback()
        alert = _find(db, user_id, game_id)
        if alert is None:
            raise
        alert.target_price_krw = target_price_krw
        alert.active = True
        db.commit()
    db.refresh(alert)
    return alert


def patch(
    db: Session,
    user_id: int,
    alert_id: int,
    target_price_krw: int | None,
    active: bool | None,
) -> Alert:
    """내 알림만 고친다. 없거나 남의 것이면 둘 다 404 (존재 여부를 알려 주지 않는다)."""
    alert = db.get(Alert, alert_id)
    if alert is None or alert.user_id != user_id:
        raise ApiError(404, "NOT_FOUND", "알림을 찾을 수 없습니다")
    if target_price_krw is not None:
        _check_price(target_price_krw)
        alert.target_price_krw = target_price_krw
    if active is not None:
        alert.active = active
    db.commit()
    db.refresh(alert)
    return alert


def remove(db: Session, user_id: int, alert_id: int) -> None:
    """내 알림을 지운다. 없거나 남의 것이면 둘 다 404 (존재 여부를 알려 주지 않는다).

    alert_logs는 erd.sql의 FK(ON DELETE CASCADE)로 함께 지워진다. DB 설정에 기대지 않고
    여기서도 먼저 지워서 어느 DB에서나 같게 동작한다.
    """
    alert = db.get(Alert, alert_id)
    if alert is None or alert.user_id != user_id:
        raise ApiError(404, "NOT_FOUND", "알림을 찾을 수 없습니다")
    db.execute(delete(AlertLog).where(AlertLog.alert_id == alert_id))
    db.delete(alert)
    db.commit()
