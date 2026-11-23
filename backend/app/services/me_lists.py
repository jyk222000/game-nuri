"""내 찜 목록(#18), 목표가 목록(#20), 알림 내역(#21).

본인 데이터라서 Primary 세션으로 읽는다(복제 지연). games·prices_current 등은 읽기만 한다.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Alert, AlertLog, Wishlist
from app.schemas.game import Card
from app.schemas.me import AlertListItem, AlertLogItem
from app.services import cards


def wishlist_cards(db: Session, user_id: int) -> list[Card]:
    """찜한 게임 카드, 최근에 찜한 순. games에 없는 게임은 건너뛴다."""
    rows = db.execute(
        select(Wishlist.game_id)
        .where(Wishlist.user_id == user_id)
        .order_by(Wishlist.created_at.desc(), Wishlist.game_id.desc())
    ).all()
    ids = [r[0] for r in rows]
    return cards.build_cards(db, ids, wished_ids=set(ids))


def alert_items(db: Session, user_id: int) -> list[AlertListItem]:
    """내 목표가 알림, 최근에 만든 순. current_krw는 새 상품 현재 최저가."""
    alerts = db.scalars(
        select(Alert).where(Alert.user_id == user_id).order_by(Alert.alert_id.desc())
    ).all()
    ids = [a.game_id for a in alerts]
    games = cards.games_by_id(db, ids)
    prices = cards.lowest_new_prices(db, ids)
    return [
        AlertListItem(
            alert_id=a.alert_id,
            game_id=a.game_id,
            game_name=cards.game_name(games[a.game_id]) if a.game_id in games else None,
            target_price_krw=a.target_price_krw,
            current_krw=prices[a.game_id].price_krw if a.game_id in prices else None,
            active=a.active,
            created_at=a.created_at,
        )
        for a in alerts
    ]


def alert_log_items(db: Session, user_id: int) -> list[AlertLogItem]:
    """알림 발송 내역, 최신순. alert_logs에 alerts·games를 조인해 game_id, game_name,
    target_price_krw를 채운다. channel은 email 고정."""
    rows = db.execute(
        select(AlertLog, Alert)
        .join(Alert, Alert.alert_id == AlertLog.alert_id)
        .where(Alert.user_id == user_id)
        .order_by(AlertLog.sent_at.desc(), AlertLog.log_id.desc())
    ).all()
    games = cards.games_by_id(db, [alert.game_id for _, alert in rows])
    return [
        AlertLogItem(
            log_id=log.log_id,
            game_id=alert.game_id,
            game_name=cards.game_name(games[alert.game_id]) if alert.game_id in games else None,
            price_krw=log.price_krw,
            target_price_krw=alert.target_price_krw,
            store=log.store,
            sent_at=log.sent_at,
        )
        for log, alert in rows
    ]
