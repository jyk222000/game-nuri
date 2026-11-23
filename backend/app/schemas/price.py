"""가격 API 응답 모양 (docs/contracts/api.md '가격 키' 절)."""

from pydantic import BaseModel

from app.core.timeutil import UtcDatetime


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
