"""가격 API 응답 모양 (docs/contracts/api.md '가격 키' 절)."""

from pydantic import BaseModel

from app.core.timeutil import UtcDatetime
from app.schemas.game import Card


class PriceItem(BaseModel):
    store: str
    edition: str  # digital | physical | code
    platform: str  # ERD 코드 (PC, PS5 ...)
    item_condition: str  # new | used
    price_krw: int
    regular_krw: int | None
    discount_pct: int | None
    url: str | None
    collected_at: UtcDatetime


class LowestNow(BaseModel):
    store: str
    edition: str
    platform: str
    item_condition: str
    price_krw: int


class PricesOut(BaseModel):
    game_id: int
    items: list[PriceItem]
    lowest: LowestNow | None  # 새 상품 최저가(현재가 정의). 새 상품이 없으면 null


class HistoryItem(BaseModel):
    store: str
    edition: str
    collected_at: UtcDatetime
    price_krw: int
    regular_krw: int | None
    discount_pct: int | None


class HistoryOut(BaseModel):
    game_id: int
    days: int
    platform: str | None  # 요청한 필터. 없으면 null
    item_condition: str | None
    items: list[HistoryItem]


class LowestItem(BaseModel):
    platform: str
    item_condition: str
    store: str
    edition: str
    price_krw: int
    regular_krw: int | None
    discount_pct: int | None
    date: str  # 최저가를 처음 수집한 날 YYYY-MM-DD (UTC)


class LowestOut(BaseModel):
    game_id: int
    items: list[LowestItem]


class DealsOut(BaseModel):
    items: list[Card]


class ExchangeRatesOut(BaseModel):
    base: str = "KRW"
    rates: dict[str, float]  # USD·EUR·GBP, 1단위당 원
    updated_at: UtcDatetime | None  # 가장 최근 환율 기준일 00:00 UTC. 환율이 없으면 null
