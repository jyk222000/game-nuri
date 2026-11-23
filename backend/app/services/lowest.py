"""역대 최저가(#12): platform·item_condition별로 price_history의 최저가 한 건.

콘솔은 이력이 짧아 '수집 이후 최저가'다(화면 문구는 프런트). 같은 최저가가 여러 번이면
가장 먼저 기록된 건(날짜가 빠른 것)을, 그래도 같으면 store·edition 이름순 첫 건을 쓴다.
"""

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.db.models import PriceHistory
from app.schemas.price import LowestItem, LowestOut
from app.services import games


def get_lowest(db: Session, game_id: int) -> LowestOut:
    games.ensure_exists(db, game_id)
    mins = (
        select(
            PriceHistory.platform.label("platform"),
            PriceHistory.item_condition.label("item_condition"),
            func.min(PriceHistory.price_krw).label("min_price"),
        )
        .where(PriceHistory.game_id == game_id)
        .group_by(PriceHistory.platform, PriceHistory.item_condition)
        .subquery()
    )
    rows = db.scalars(
        select(PriceHistory)
        .join(
            mins,
            and_(
                PriceHistory.platform == mins.c.platform,
                PriceHistory.item_condition == mins.c.item_condition,
                PriceHistory.price_krw == mins.c.min_price,
            ),
        )
        .where(PriceHistory.game_id == game_id)
        .order_by(PriceHistory.collected_at, PriceHistory.store, PriceHistory.edition)
    ).all()
    best: dict[tuple[str, str], PriceHistory] = {}
    for r in rows:  # 정렬돼 있어 그룹의 첫 행이 가장 이른 최저가
        best.setdefault((r.platform, r.item_condition), r)
    items = [
        LowestItem(
            platform=r.platform,
            item_condition=r.item_condition,
            store=r.store,
            edition=r.edition,
            price_krw=r.price_krw,
            regular_krw=r.regular_krw,
            discount_pct=r.discount_pct,
            date=r.collected_at.strftime("%Y-%m-%d"),
        )
        for _, r in sorted(best.items())
    ]
    return LowestOut(game_id=game_id, items=items)
