"""게임 상세(#7). 카드 필드 + 출시일·소개·태그·Steam 앱 ID·역대 최저가. 읽기만 한다."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    GameStoreId,
    GameTag,
    GameTimeToBeat,
    PriceCurrent,
    PriceHistory,
    Tag,
)
from app.schemas.game import GameDetail, TimeToBeat
from app.services import cards, games


def _lowest_krw(db: Session, game_id: int) -> int | None:
    """새 상품 역대 최저가. 이력 최저와 현재가 중 낮은 쪽.

    카드 현재가와 같은 기준: PC 가격(이력·현재가)이 있으면 PC 안에서, 없으면(콘솔 전용) 전체 플랫폼.
    """

    def _min(platform: str | None) -> int | None:
        hist_where = [PriceHistory.game_id == game_id, PriceHistory.item_condition == "new"]
        now_where = [PriceCurrent.game_id == game_id, PriceCurrent.item_condition == "new"]
        if platform is not None:
            hist_where.append(PriceHistory.platform == platform)
            now_where.append(PriceCurrent.platform == platform)
        found = [
            v
            for v in (
                db.scalar(select(func.min(PriceHistory.price_krw)).where(*hist_where)),
                db.scalar(select(func.min(PriceCurrent.price_krw)).where(*now_where)),
            )
            if v is not None
        ]
        return min(found) if found else None

    pc = _min(cards.PRIMARY_PLATFORM)
    return pc if pc is not None else _min(None)


def _hours(seconds: int | None) -> float | None:
    """초 → 시간(소수 첫째 자리). 짧은 게임이 0시간으로 보이지 않게 한다. 0이거나 없으면 None."""
    return round(seconds / 3600, 1) if seconds else None


def _time_to_beat(db: Session, game_id: int) -> TimeToBeat | None:
    row = db.get(GameTimeToBeat, game_id)
    if row is None:
        return None
    return TimeToBeat(
        hastily_hours=_hours(row.hastily_sec),
        normally_hours=_hours(row.normally_sec),
        completely_hours=_hours(row.completely_sec),
        count=row.ttb_count or None,
    )


def get_detail(db: Session, game_id: int) -> GameDetail:
    game = games.ensure_exists(db, game_id)
    card = cards.build_cards(db, [game_id], wished_ids=set())[0]
    tag_rows = db.execute(
        select(Tag.name, Tag.name_ko)
        .join(GameTag, GameTag.tag_id == Tag.tag_id)
        .where(GameTag.game_id == game_id)
    ).all()
    steam = db.scalar(
        select(GameStoreId.external_id)
        .where(GameStoreId.game_id == game_id, GameStoreId.store == "steam")
        .order_by(GameStoreId.external_id)
    )
    return GameDetail(
        **card.model_dump(),
        time_to_beat=_time_to_beat(db, game_id),
        critic_count=game.aggregated_rating_count if game.aggregated_rating is not None else None,
        release_date=game.release_date.isoformat() if game.release_date else None,
        summary=game.summary,
        tags=sorted({ko or name for name, ko in tag_rows}),
        online_only=bool(game.is_online),
        steam_app_id=int(steam) if steam is not None and steam.isdigit() else None,
        lowest_krw=_lowest_krw(db, game_id),
        insights=[],
    )
