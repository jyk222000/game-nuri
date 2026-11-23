"""할인 중 목록(#13). 새 상품 현재가(카드의 price_krw)가 할인 중인 게임을 할인율 큰 순으로.

로그인 없이 보는 목록이라 wished는 항상 false다. prices_current는 읽기만 한다.
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import PriceCurrent
from app.schemas.game import Card
from app.services import cards

CANDIDATE_LIMIT = 200  # 할인율 상위 후보만 카드로 만든다


def get_deals(db: Session, size: int) -> list[Card]:
    rows = db.execute(
        select(PriceCurrent.game_id)
        .where(PriceCurrent.item_condition == "new", PriceCurrent.discount_pct > 0)
        .group_by(PriceCurrent.game_id)
        .order_by(func.max(PriceCurrent.discount_pct).desc(), PriceCurrent.game_id)
        .limit(CANDIDATE_LIMIT)
    ).all()
    built = cards.build_cards(db, [r[0] for r in rows], wished_ids=set())
    # 카드의 현재가(새 상품 최저가)가 실제로 할인 중인 게임만 남긴다.
    deals = [c for c in built if c.discount_pct is not None and c.discount_pct > 0]
    deals.sort(key=lambda c: (-(c.discount_pct or 0), c.game_id))
    return deals[:size]
