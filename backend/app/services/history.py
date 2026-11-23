"""가격 이력(#11). price_history는 읽기만 한다.

price_history에는 UNIQUE 키가 없어 같은 줄이 여러 번 들어올 수 있다. 응답 전에
(game_id, store, edition, platform, item_condition, collected_at)이 같은 줄을 하나로 합친다
(가장 나중에 들어온 행 = id가 가장 큰 행). edition만 다른 행은 서로 다른 행이다.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import PriceHistory
from app.schemas.price import HistoryItem, HistoryOut
from app.services import games


def dedupe(rows: list[PriceHistory]) -> list[PriceHistory]:
    """같은 키는 id가 가장 큰 행 하나만 남기고, 수집 시각 순으로 돌려준다."""
    latest: dict[tuple, PriceHistory] = {}
    for r in rows:
        key = (r.game_id, r.store, r.edition, r.platform, r.item_condition, r.collected_at)
        if key not in latest or r.id > latest[key].id:
            latest[key] = r
    return sorted(
        latest.values(), key=lambda r: (r.collected_at, r.store, r.edition, r.platform, r.id)
    )


def get_history(
    db: Session,
    game_id: int,
    days: int,
    platform: str | None,
    item_condition: str | None,
    now: datetime | None = None,
) -> HistoryOut:
    games.ensure_exists(db, game_id)
    now = now or datetime.now(UTC).replace(tzinfo=None)  # DB는 UTC naive
    query = select(PriceHistory).where(
        PriceHistory.game_id == game_id,
        PriceHistory.collected_at >= now - timedelta(days=days),
    )
    if platform is not None:
        query = query.where(PriceHistory.platform == platform)
    if item_condition is not None:
        query = query.where(PriceHistory.item_condition == item_condition)
    rows = dedupe(list(db.scalars(query)))
    return HistoryOut(
        game_id=game_id,
        days=days,
        platform=platform,
        item_condition=item_condition,
        items=[
            HistoryItem(
                store=r.store,
                edition=r.edition,
                collected_at=r.collected_at,
                price_krw=r.price_krw,
                regular_krw=r.regular_krw,
                discount_pct=r.discount_pct,
            )
            for r in rows
        ],
    )
