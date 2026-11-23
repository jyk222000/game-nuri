"""게임·코드·검색 보조 테이블 (erd.sql 1장).

**읽기 전용**: Backend는 쓰지 않는다 (Kafka Connect가 쓴다).

컬럼 이름·타입·키는 docs/contracts/erd.sql 그대로다 (tests/test_models_erd.py가 비교한다).
"""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    DECIMAL,
    Boolean,
    Date,
    DateTime,
    Enum,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    false,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, BigIntPk


class Game(Base):
    __tablename__ = "games"
    __table_args__ = (
        Index("idx_games_name", "name"),
        Index("idx_games_parent", "parent_game_id"),
    )

    game_id: Mapped[int] = mapped_column(BigIntPk, primary_key=True, autoincrement=False)
    name: Mapped[str] = mapped_column(String(255))  # 영문 이름
    name_ko: Mapped[str | None] = mapped_column(String(255))
    slug: Mapped[str | None] = mapped_column(String(255))
    summary: Mapped[str | None] = mapped_column(Text)
    release_date: Mapped[date | None] = mapped_column(Date)
    game_type: Mapped[int | None] = mapped_column(SmallInteger)
    parent_game_id: Mapped[int | None] = mapped_column(BigIntPk)
    version_parent_id: Mapped[int | None] = mapped_column(BigIntPk)
    cover_image_id: Mapped[str | None] = mapped_column(String(64))
    cover_url: Mapped[str | None] = mapped_column(String(512))
    rating: Mapped[Decimal | None] = mapped_column(DECIMAL(5, 2))
    rating_count: Mapped[int | None] = mapped_column(Integer)
    aggregated_rating: Mapped[Decimal | None] = mapped_column(DECIMAL(5, 2))
    aggregated_rating_count: Mapped[int | None] = mapped_column(Integer)
    age_rating: Mapped[int | None] = mapped_column(SmallInteger)
    korean_supported: Mapped[bool | None] = mapped_column(Boolean)
    is_online: Mapped[bool | None] = mapped_column(Boolean)
    updated_at: Mapped[datetime] = mapped_column(DateTime)


class Platform(Base):
    __tablename__ = "platforms"

    platform: Mapped[str] = mapped_column(String(16), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(64))


class Genre(Base):
    __tablename__ = "genres"

    genre_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    name: Mapped[str] = mapped_column(String(64))


class Company(Base):
    __tablename__ = "companies"

    company_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), unique=True)


class GamePlatform(Base):
    __tablename__ = "game_platforms"

    game_id: Mapped[int] = mapped_column(BigIntPk, primary_key=True, autoincrement=False)
    platform: Mapped[str] = mapped_column(String(16), primary_key=True)
    release_date: Mapped[date | None] = mapped_column(Date)


class GameGenre(Base):
    __tablename__ = "game_genres"

    game_id: Mapped[int] = mapped_column(BigIntPk, primary_key=True, autoincrement=False)
    genre_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)


class GameCompany(Base):
    __tablename__ = "game_companies"

    game_id: Mapped[int] = mapped_column(BigIntPk, primary_key=True, autoincrement=False)
    company_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    role: Mapped[str] = mapped_column(String(16), primary_key=True)  # developer | publisher


class GameAlias(Base):
    __tablename__ = "game_aliases"
    __table_args__ = (
        UniqueConstraint("game_id", "alias", name="uq_game_alias"),
        Index("idx_alias", "alias"),
    )

    alias_id: Mapped[int] = mapped_column(BigIntPk, primary_key=True, autoincrement=True)
    game_id: Mapped[int] = mapped_column(BigIntPk)
    alias: Mapped[str] = mapped_column(String(255))
    source: Mapped[str] = mapped_column(String(16))  # igdb | llm | manual
    reviewed: Mapped[bool] = mapped_column(Boolean, server_default=false())


class GameSeries(Base):
    __tablename__ = "game_series"

    series_id: Mapped[int] = mapped_column(BigIntPk, primary_key=True, autoincrement=False)
    kind: Mapped[str] = mapped_column(String(16), primary_key=True)  # collection | franchise
    name: Mapped[str] = mapped_column(String(255))


class GameSeriesMap(Base):
    __tablename__ = "game_series_map"

    game_id: Mapped[int] = mapped_column(BigIntPk, primary_key=True, autoincrement=False)
    series_id: Mapped[int] = mapped_column(BigIntPk, primary_key=True, autoincrement=False)
    kind: Mapped[str] = mapped_column(String(16), primary_key=True)


class Tag(Base):
    __tablename__ = "tags"
    __table_args__ = (UniqueConstraint("source", "name", name="uq_tag"),)

    tag_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64))
    source: Mapped[str] = mapped_column(String(16))  # igdb_theme | igdb_keyword | itad
    name_ko: Mapped[str | None] = mapped_column(String(64))


class GameTag(Base):
    __tablename__ = "game_tags"

    game_id: Mapped[int] = mapped_column(BigIntPk, primary_key=True, autoincrement=False)
    tag_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)


class Store(Base):
    __tablename__ = "stores"

    store: Mapped[str] = mapped_column(String(32), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(64))
    platform: Mapped[str] = mapped_column(Enum("pc", "console"))
    itad_shop_id: Mapped[int | None] = mapped_column(Integer, unique=True)


class GameStoreId(Base):
    __tablename__ = "game_store_ids"
    __table_args__ = (Index("idx_game", "game_id"),)

    game_id: Mapped[int] = mapped_column(BigIntPk)
    store: Mapped[str] = mapped_column(String(32), primary_key=True)
    external_id: Mapped[str] = mapped_column(String(128), primary_key=True)


class GameTimeToBeat(Base):
    __tablename__ = "game_time_to_beat"

    game_id: Mapped[int] = mapped_column(BigIntPk, primary_key=True, autoincrement=False)
    hastily_sec: Mapped[int | None] = mapped_column(Integer)
    normally_sec: Mapped[int | None] = mapped_column(Integer)
    completely_sec: Mapped[int | None] = mapped_column(Integer)
    ttb_count: Mapped[int | None] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(DateTime)


class GameRequirement(Base):
    __tablename__ = "game_requirements"

    game_id: Mapped[int] = mapped_column(BigIntPk, primary_key=True, autoincrement=False)
    minimum_text: Mapped[str | None] = mapped_column(Text)
    recommended_text: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime)


class PlayerCount(Base):
    __tablename__ = "player_counts"

    game_id: Mapped[int] = mapped_column(BigIntPk, primary_key=True, autoincrement=False)
    player_count: Mapped[int] = mapped_column(Integer)
    collected_at: Mapped[datetime] = mapped_column(DateTime, primary_key=True)


class ReviewSummary(Base):
    __tablename__ = "review_summaries"

    game_id: Mapped[int] = mapped_column(BigIntPk, primary_key=True, autoincrement=False)
    positive_ratio: Mapped[Decimal | None] = mapped_column(DECIMAL(4, 3))
    pros_keywords: Mapped[str | None] = mapped_column(String(512))
    cons_keywords: Mapped[str | None] = mapped_column(String(512))
    summary: Mapped[str | None] = mapped_column(String(1000))
    generated_by: Mapped[str] = mapped_column(String(16))  # ai | fallback
    updated_at: Mapped[datetime] = mapped_column(DateTime)


class GameReviewStats(Base):
    """Steam 스토어 리뷰 수·긍정률 (GetItems). review_summaries(AI 요약)와 game_id로 붙인다."""

    __tablename__ = "game_review_stats"

    game_id: Mapped[int] = mapped_column(BigIntPk, primary_key=True, autoincrement=False)
    review_count_ko: Mapped[int | None] = mapped_column(Integer)
    positive_pct_ko: Mapped[int | None] = mapped_column(SmallInteger)
    review_score_ko: Mapped[int | None] = mapped_column(SmallInteger)
    review_label_ko: Mapped[str | None] = mapped_column(String(32))
    review_count_all: Mapped[int | None] = mapped_column(Integer)
    positive_pct_all: Mapped[int | None] = mapped_column(SmallInteger)
    review_label_all: Mapped[str | None] = mapped_column(String(32))
    updated_at: Mapped[datetime] = mapped_column(DateTime)
