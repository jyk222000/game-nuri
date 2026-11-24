"""가격·환율 테이블 (erd.sql 2장). **읽기 전용**: Backend는 쓰지 않는다 (Kafka Connect가 쓴다).

가격 키는 (game_id, store, edition, platform, item_condition). 같은 게임의 PS4·PS5, 신품·중고가
서로 덮어쓰지 않게 platform·item_condition이 키에 들어 있다.
price_history에는 UNIQUE 키가 없다(insert 모드 Sink가 중복에서 멈추기 때문).
중복은 refiner와 조회 쪽에서 거른다.
"""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CHAR, DECIMAL, Date, DateTime, Double, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, BigIntPk


class PriceCurrent(Base):
    __tablename__ = "prices_current"

    game_id: Mapped[int] = mapped_column(BigIntPk, primary_key=True, autoincrement=False)
    store: Mapped[str] = mapped_column(String(32), primary_key=True)
    edition: Mapped[str] = mapped_column(String(16), primary_key=True)  # digital | physical | code
    platform: Mapped[str] = mapped_column(String(16), primary_key=True)
    item_condition: Mapped[str] = mapped_column(String(8), primary_key=True)  # new | used
    price_krw: Mapped[int] = mapped_column(Integer)
    regular_krw: Mapped[int | None] = mapped_column(Integer)
    discount_pct: Mapped[int | None] = mapped_column(Integer)
    price_original: Mapped[float | None] = mapped_column(Double)
    currency_original: Mapped[str | None] = mapped_column(String(8))
    url: Mapped[str | None] = mapped_column(String(512))
    variant_name: Mapped[str | None] = mapped_column(
        String(64)
    )  # 에디션 가격이면 이름, 본편은 NULL (#93)
    collected_at: Mapped[datetime] = mapped_column(DateTime)


class PriceHistory(Base):
    __tablename__ = "price_history"
    __table_args__ = (
        Index("idx_game_time", "game_id", "collected_at"),
        Index("idx_game_platform_time", "game_id", "platform", "item_condition", "collected_at"),
    )

    id: Mapped[int] = mapped_column(BigIntPk, primary_key=True, autoincrement=True)
    game_id: Mapped[int] = mapped_column(BigIntPk)
    store: Mapped[str] = mapped_column(String(32))
    edition: Mapped[str] = mapped_column(String(16))
    platform: Mapped[str] = mapped_column(String(16))
    item_condition: Mapped[str] = mapped_column(String(8))
    price_krw: Mapped[int] = mapped_column(Integer)
    regular_krw: Mapped[int | None] = mapped_column(Integer)
    discount_pct: Mapped[int | None] = mapped_column(Integer)
    price_original: Mapped[float | None] = mapped_column(Double)
    currency_original: Mapped[str | None] = mapped_column(String(8))
    url: Mapped[str | None] = mapped_column(String(512))
    variant_name: Mapped[str | None] = mapped_column(
        String(64)
    )  # 에디션 가격이면 이름, 본편은 NULL (#93)
    collected_at: Mapped[datetime] = mapped_column(DateTime)


class ExchangeRate(Base):
    __tablename__ = "exchange_rates"

    rate_date: Mapped[date] = mapped_column(Date, primary_key=True)
    currency: Mapped[str] = mapped_column(CHAR(3), primary_key=True)  # USD, EUR, GBP
    krw_per_unit: Mapped[Decimal] = mapped_column(DECIMAL(12, 4))
