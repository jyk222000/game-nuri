"""게임 카드·현재가 조회. 게임·가격 테이블은 읽기만 한다 (쓰지 않는다).

현재가 규칙(제안, api.md 확정 전): prices_current에서 item_condition='new'인 행 중
price_krw가 가장 낮은 것. 같으면 store, platform 이름순.
"""

from collections.abc import Iterable

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.db.models import (
    Game,
    GameGenre,
    GamePlatform,
    GameTimeToBeat,
    Genre,
    PlayerCount,
    PriceCurrent,
    ReviewSummary,
)
from app.schemas.game import Card


def game_name(game: Game) -> str:
    return game.name_ko or game.name


def lowest_new_prices(db: Session, game_ids: Iterable[int]) -> dict[int, PriceCurrent]:
    """게임별 현재 최저가 행 (새 상품 기준)."""
    ids = list(set(game_ids))
    if not ids:
        return {}
    rows = db.scalars(
        select(PriceCurrent).where(
            PriceCurrent.game_id.in_(ids), PriceCurrent.item_condition == "new"
        )
    ).all()
    best: dict[int, PriceCurrent] = {}
    for row in rows:
        cur = best.get(row.game_id)
        if cur is None or (row.price_krw, row.store, row.platform) < (
            cur.price_krw,
            cur.store,
            cur.platform,
        ):
            best[row.game_id] = row
    return best


def games_by_id(db: Session, game_ids: Iterable[int]) -> dict[int, Game]:
    ids = list(set(game_ids))
    if not ids:
        return {}
    return {g.game_id: g for g in db.scalars(select(Game).where(Game.game_id.in_(ids)))}


def build_cards(db: Session, game_ids: list[int], wished_ids: set[int]) -> list[Card]:
    """game_ids 순서대로 카드를 만든다. games에 없는 id는 건너뛴다."""
    games = games_by_id(db, game_ids)
    ids = [i for i in game_ids if i in games]
    if not ids:
        return []

    genres: dict[int, list[str]] = {}
    for gid, name in db.execute(
        select(GameGenre.game_id, Genre.name)
        .join(Genre, Genre.genre_id == GameGenre.genre_id)
        .where(GameGenre.game_id.in_(ids))
        .order_by(Genre.genre_id)
    ):
        genres.setdefault(gid, []).append(name)

    platforms: dict[int, list[str]] = {}
    for gid, platform in db.execute(
        select(GamePlatform.game_id, GamePlatform.platform)
        .where(GamePlatform.game_id.in_(ids))
        .order_by(GamePlatform.platform)
    ):
        platforms.setdefault(gid, []).append(platform)

    prices = lowest_new_prices(db, ids)

    ratio = {
        gid: value
        for gid, value in db.execute(
            select(ReviewSummary.game_id, ReviewSummary.positive_ratio).where(
                ReviewSummary.game_id.in_(ids)
            )
        )
    }

    latest = (
        select(PlayerCount.game_id, func.max(PlayerCount.collected_at).label("latest"))
        .where(PlayerCount.game_id.in_(ids))
        .group_by(PlayerCount.game_id)
        .subquery()
    )
    players = dict(
        db.execute(
            select(PlayerCount.game_id, PlayerCount.player_count).join(
                latest,
                and_(
                    PlayerCount.game_id == latest.c.game_id,
                    PlayerCount.collected_at == latest.c.latest,
                ),
            )
        ).all()
    )

    ttb = dict(
        db.execute(
            select(GameTimeToBeat.game_id, GameTimeToBeat.normally_sec).where(
                GameTimeToBeat.game_id.in_(ids)
            )
        ).all()
    )

    cards = []
    for gid in ids:
        game, price = games[gid], prices.get(gid)
        seconds = ttb.get(gid)
        cards.append(
            Card(
                game_id=gid,
                name=game_name(game),
                name_en=game.name,
                genres=genres.get(gid, []),
                platforms=platforms.get(gid, []),
                cover_url=game.cover_url,
                price_krw=price.price_krw if price else None,
                regular_krw=price.regular_krw if price else None,
                discount_pct=price.discount_pct if price else None,
                positive_ratio=float(ratio[gid]) if ratio.get(gid) is not None else None,
                concurrent_players=players.get(gid),
                time_to_beat_hours=round(seconds / 3600) if seconds else None,
                wished=gid in wished_ids,
            )
        )
    return cards
