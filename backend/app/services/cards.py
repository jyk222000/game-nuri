"""게임 카드·현재가 조회. 게임·가격 테이블은 읽기만 한다 (쓰지 않는다).

현재가 규칙(제안, api.md 확정 전): prices_current에서 item_condition='new'인 행 중
price_krw가 가장 낮은 것. 같으면 store, platform 이름순.
**PC 가격이 있으면 PC 안에서만 고른다**(PRIMARY_PLATFORM). 콘솔(다나와)은 정가·할인율이 없어
섞이면 카드의 할인 표시가 사라지고 구매 타이밍(PC 기준)의 현재가와 어긋난다. PC 가격이 없는
게임(콘솔 전용)은 전체 플랫폼 최저가를 쓴다. 콘솔 가격은 /prices, /lowest의 플랫폼별 값에 남는다.
"""

from collections.abc import Iterable
from decimal import Decimal

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
)
from app.schemas.game import Card
from app.services import ratings

# 카드·구매 타이밍(timing.TIMING_PLATFORM)이 현재가·역대 최저가를 보는 기준 플랫폼
PRIMARY_PLATFORM = "PC"


def game_name(game: Game) -> str:
    return game.name_ko or game.name


def _keep_lowest(best: dict[int, PriceCurrent], row: PriceCurrent) -> None:
    cur = best.get(row.game_id)
    if cur is None or (row.price_krw, row.store, row.platform) < (
        cur.price_krw,
        cur.store,
        cur.platform,
    ):
        best[row.game_id] = row


def lowest_new_prices(db: Session, game_ids: Iterable[int]) -> dict[int, PriceCurrent]:
    """게임별 현재 최저가 행 (새 상품 기준, PC 우선 — 모듈 설명 참고)."""
    ids = list(set(game_ids))
    if not ids:
        return {}
    rows = db.scalars(
        select(PriceCurrent).where(
            PriceCurrent.game_id.in_(ids), PriceCurrent.item_condition == "new"
        )
    ).all()
    best_any: dict[int, PriceCurrent] = {}
    best_pc: dict[int, PriceCurrent] = {}
    for row in rows:
        _keep_lowest(best_any, row)
        if row.platform == PRIMARY_PLATFORM:
            _keep_lowest(best_pc, row)
    return {**best_any, **best_pc}  # PC 가격이 있는 게임은 PC 값이 이긴다


def critic_score(rating: Decimal | float | None) -> int | None:
    """IGDB 평론가 집계 점수(0~100)를 정수로 반올림한다(.5는 올림). 값이 없으면 None."""
    if rating is None:
        return None
    return int(Decimal(str(rating)) + Decimal("0.5"))


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

    ratio = ratings.positive_ratios(db, ids)

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
                positive_ratio=ratio.get(gid),
                concurrent_players=players.get(gid),
                time_to_beat_hours=round(seconds / 3600) if seconds else None,
                critic_score=critic_score(game.aggregated_rating),
                wished=gid in wished_ids,
            )
        )
    return cards
