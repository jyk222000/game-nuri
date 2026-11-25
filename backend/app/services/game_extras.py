"""게임 상세에 붙는 부가 정보: 개발사·배급사, 시리즈, DLC·에디션 관계, Steam 리뷰 등급. 읽기만 한다.

모두 DB에 이미 있는 칸을 그대로 내려 주는 것이다(새 API 없음). 값이 없으면 빈 목록이나 null이다.
"""

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Company,
    Game,
    GameCompany,
    GameReviewStats,
    GameSeries,
    GameSeriesMap,
)
from app.schemas.game import RelatedGame, ReviewStatsOut, SeriesOut
from app.services import cards

SERIES_GAMES_MAX = 12  # 시리즈마다 보여 줄 다른 게임 수
RELATED_MAX = 20  # DLC·에디션 목록 최대 수


def _related(game: Game) -> RelatedGame:
    return RelatedGame(game_id=game.game_id, name=cards.game_name(game), cover_url=game.cover_url)


def user_score(rating: Decimal | float | None) -> int | None:
    """IGDB 사용자 평점(0~100)을 정수로 반올림한다. 없으면 None."""
    return cards.critic_score(rating)


def companies(db: Session, game_id: int) -> tuple[list[str], list[str]]:
    """(개발사 이름들, 배급사 이름들). 이름순."""
    rows = db.execute(
        select(GameCompany.role, Company.name)
        .join(Company, Company.company_id == GameCompany.company_id)
        .where(GameCompany.game_id == game_id)
        .order_by(Company.name)
    ).all()
    developers = [name for role, name in rows if role == "developer"]
    publishers = [name for role, name in rows if role == "publisher"]
    return developers, publishers


def series(db: Session, game_id: int) -> list[SeriesOut]:
    """이 게임이 속한 시리즈(collection·franchise)와 같은 시리즈의 다른 게임(최대 12개)."""
    mine = db.execute(
        select(GameSeries.series_id, GameSeries.kind, GameSeries.name)
        .join(
            GameSeriesMap,
            (GameSeriesMap.series_id == GameSeries.series_id)
            & (GameSeriesMap.kind == GameSeries.kind),
        )
        .where(GameSeriesMap.game_id == game_id)
        .order_by(GameSeries.kind, GameSeries.name)
    ).all()
    out = []
    for series_id, kind, name in mine:
        others = db.scalars(
            select(Game)
            .join(GameSeriesMap, GameSeriesMap.game_id == Game.game_id)
            .where(
                GameSeriesMap.series_id == series_id,
                GameSeriesMap.kind == kind,
                Game.game_id != game_id,
            )
            .order_by(Game.release_date.is_(None), Game.release_date, Game.name, Game.game_id)
            .limit(SERIES_GAMES_MAX)
        ).all()
        out.append(SeriesOut(kind=kind, name=name, games=[_related(g) for g in others]))
    return out


def relations(
    db: Session, game: Game
) -> tuple[RelatedGame | None, RelatedGame | None, list[RelatedGame], list[RelatedGame]]:
    """(DLC의 본편, 에디션의 원본, 이 게임의 DLC들, 이 게임의 에디션들). games에 없는 ID는 None."""
    parent = db.get(Game, game.parent_game_id) if game.parent_game_id else None
    version_parent = db.get(Game, game.version_parent_id) if game.version_parent_id else None
    dlcs = db.scalars(
        select(Game)
        .where(Game.parent_game_id == game.game_id)
        .order_by(Game.release_date.is_(None), Game.release_date, Game.name, Game.game_id)
        .limit(RELATED_MAX)
    ).all()
    editions = db.scalars(
        select(Game)
        .where(Game.version_parent_id == game.game_id)
        .order_by(Game.name, Game.game_id)
        .limit(RELATED_MAX)
    ).all()
    return (
        _related(parent) if parent else None,
        _related(version_parent) if version_parent else None,
        [_related(g) for g in dlcs],
        [_related(g) for g in editions],
    )


def review_stats(db: Session, game_id: int) -> ReviewStatsOut | None:
    """Steam 스토어 리뷰 등급·수(한국어 / 전체 언어). 행이 없으면 None."""
    row = db.get(GameReviewStats, game_id)
    if row is None:
        return None
    return ReviewStatsOut(
        label_ko=row.review_label_ko,
        count_ko=row.review_count_ko,
        positive_pct_ko=row.positive_pct_ko,
        score_ko=row.review_score_ko,
        label_all=row.review_label_all,
        count_all=row.review_count_all,
        positive_pct_all=row.positive_pct_all,
    )
