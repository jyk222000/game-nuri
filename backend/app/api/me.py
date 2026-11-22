"""내 정보 라우터: 찜(#17), 목표가 알림 설정·수정(#19), 메일 수신 설정(#22). 모두 로그인 필요.

본인 데이터는 복제 지연 때문에 쓰기(Primary) 세션으로 읽고 쓴다. 로직은 services/에 둔다.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_current_user
from app.db.session import get_write_db
from app.schemas.me import (
    AlertCreate,
    AlertOut,
    AlertPatch,
    NotificationBody,
    NotificationOut,
    WishlistAdd,
    WishlistState,
)
from app.services import alerts, notifications, wishlist

router = APIRouter(prefix="/api/me")

User = Annotated[CurrentUser, Depends(get_current_user)]
Db = Annotated[Session, Depends(get_write_db)]


def _alert_out(alert) -> AlertOut:  # noqa: ANN001
    return AlertOut(
        alert_id=alert.alert_id,
        game_id=alert.game_id,
        target_price_krw=alert.target_price_krw,
        active=alert.active,
        created_at=alert.created_at,
    )


# ---- #17 찜 ----
@router.post("/wishlist", response_model=WishlistState)
def add_wish(body: WishlistAdd, user: User, db: Db) -> WishlistState:
    wishlist.add(db, user.user_id, body.game_id)
    return WishlistState(game_id=body.game_id, wished=True)


@router.delete("/wishlist", response_model=WishlistState)
def remove_wish(game_id: Annotated[int, Query(gt=0)], user: User, db: Db) -> WishlistState:
    wishlist.remove(db, user.user_id, game_id)
    return WishlistState(game_id=game_id, wished=False)


# ---- #19 목표가 알림 (POST·PATCH. DELETE는 보류) ----
@router.post("/alerts", response_model=AlertOut)
def set_alert(body: AlertCreate, user: User, db: Db) -> AlertOut:
    return _alert_out(alerts.upsert(db, user.user_id, body.game_id, body.target_price_krw))


@router.patch("/alerts/{alert_id}", response_model=AlertOut)
def patch_alert(alert_id: int, body: AlertPatch, user: User, db: Db) -> AlertOut:
    return _alert_out(alerts.patch(db, user.user_id, alert_id, body.target_price_krw, body.active))


# ---- #22 메일 수신 설정 ----
@router.get("/notifications", response_model=NotificationOut)
def get_notifications(user: User, db: Db) -> NotificationOut:
    return NotificationOut(email_enabled=notifications.get_email_enabled(db, user.user_id))


@router.put("/notifications", response_model=NotificationOut)
def put_notifications(body: NotificationBody, user: User, db: Db) -> NotificationOut:
    enabled = notifications.set_email_enabled(db, user.user_id, body.email_enabled)
    return NotificationOut(email_enabled=enabled)
