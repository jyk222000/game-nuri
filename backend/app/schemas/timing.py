"""구매 타이밍(#15)·할인 예측(#16) 응답 모양 (docs/contracts/api.md '구매 타이밍' 절)."""

from typing import Literal

from pydantic import BaseModel


class TimingOut(BaseModel):
    game_id: int
    verdict: Literal["buy_now", "neutral", "wait", "insufficient_data"]
    reason: str
    # insufficient_data이면 계산할 수 없는 값은 null
    current_krw: int | None
    lowest_krw: int | None
    lowest_date: str | None  # YYYY-MM-DD (UTC)
    vs_lowest_pct: int | None
    sale_count_2y: int | None


class PredictionOut(BaseModel):
    game_id: int
    # 이력이 부족하면(confidence = "insufficient_data") 값 필드는 null
    avg_sale_interval_days: int | None
    next_sale_expected: str | None  # YYYY-MM-DD (UTC)
    expected_discount_pct: int | None
    confidence: Literal["high", "medium", "low", "insufficient_data"]
    basis: str
