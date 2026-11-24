"""스토어별 가격 비교(#10). prices_current는 읽기만 한다.

결과는 Valkey `cache:prices:{game_id}`에 10분 저장한다. Valkey가 죽어도 503을 내지 않고
캐시를 건너뛰어 DB에서 읽는다(fail-open). 존재하지 않는 게임은 캐시에 넣지 않는다.
"""

import logging

import redis
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.clients.valkey import get_valkey
from app.core import keys
from app.db.models import PriceCurrent
from app.schemas.price import LowestNow, PriceItem, PricesOut
from app.services import cards, games

log = logging.getLogger(__name__)


def _cache_get(game_id: int) -> PricesOut | None:
    try:
        raw = get_valkey().get(keys.price_cache_key(game_id))
    except redis.RedisError as exc:
        log.warning("가격 캐시 읽기 실패, DB로 진행: %s", type(exc).__name__)
        return None
    if raw is None:
        return None
    try:
        return PricesOut.model_validate_json(raw)
    except ValidationError:
        log.warning("가격 캐시 값이 올바르지 않아 무시함: game_id=%s", game_id)
        return None


def _cache_set(game_id: int, value: PricesOut) -> None:
    try:
        get_valkey().set(
            keys.price_cache_key(game_id),
            value.model_dump_json(),
            ex=keys.PRICE_CACHE_TTL_SECONDS,
        )
    except redis.RedisError as exc:
        log.warning("가격 캐시 쓰기 실패, 건너뜀: %s", type(exc).__name__)


def get_prices(db: Session, game_id: int) -> PricesOut:
    cached = _cache_get(game_id)
    if cached is not None:
        return cached

    games.ensure_exists(db, game_id)  # 없으면 404 (캐시에는 넣지 않는다)
    rows = db.scalars(
        select(PriceCurrent)
        .where(PriceCurrent.game_id == game_id)
        .order_by(
            PriceCurrent.price_krw,
            PriceCurrent.store,
            PriceCurrent.platform,
            PriceCurrent.edition,
            PriceCurrent.item_condition,
        )
    ).all()
    items = [
        PriceItem(
            store=r.store,
            edition=r.edition,
            platform=r.platform,
            item_condition=r.item_condition,
            price_krw=r.price_krw,
            regular_krw=r.regular_krw,
            discount_pct=r.discount_pct,
            url=r.url,
            collected_at=r.collected_at,
        )
        for r in rows
    ]
    new_items = [i for i in items if i.item_condition == "new"]  # 가격순으로 정렬돼 있다
    # 현재가(lowest)는 카드·구매 타이밍과 같은 기준: PC 새 상품이 있으면 PC 안에서, 없으면 전체에서.
    pc_items = [i for i in new_items if i.platform == cards.PRIMARY_PLATFORM]
    pick = (pc_items or new_items)[:1]
    lowest = (
        LowestNow(
            store=pick[0].store,
            edition=pick[0].edition,
            platform=pick[0].platform,
            item_condition="new",
            price_krw=pick[0].price_krw,
        )
        if pick
        else None
    )
    out = PricesOut(game_id=game_id, items=items, lowest=lowest)
    _cache_set(game_id, out)
    return out
