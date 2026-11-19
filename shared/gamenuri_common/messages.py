"""Kafka 메시지 모델. docs/contracts/ 와 반드시 일치시킨다."""

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

Source = Literal["itad", "danawa", "steam", "igdb"]
Kind = Literal[
    "price",
    "console_price",
    "review",
    "owned_games",
    "game_info",
    "app_details",
    "player_count",
    "time_to_beat",
]

TOPIC_RAW = {"itad": "raw.price", "danawa": "raw.console", "steam": "raw.steam", "igdb": "raw.igdb"}
TOPIC_REFINED_GAMES = "refined.games"
TOPIC_REFINED_PRICES = "refined.prices"
TOPIC_REFINED_REQUIREMENTS = "refined.requirements"
TOPIC_REFINED_REVIEW_SUMMARY = "refined.review_summary"
TOPIC_REFINED_UNMATCHED = "refined.unmatched"
TOPIC_CLICKSTREAM = "clickstream"


def utcnow() -> datetime:
    return datetime.now(UTC)


class RawEnvelope(BaseModel):
    """raw.* 공통 봉투. payload에는 원본을 그대로 담는다."""

    schema_version: int = 1
    source: Source
    kind: Kind
    collected_at: datetime = Field(default_factory=utcnow)
    request: dict[str, Any] = Field(default_factory=dict)
    payload: dict[str, Any]


class RefinedPrice(BaseModel):
    game_id: int
    store: str
    edition: Literal["digital", "physical", "code"]
    price_krw: int
    regular_krw: int | None = None
    discount_pct: int | None = None
    price_original: float | None = None
    currency_original: str | None = None
    url: str | None = None
    collected_at: datetime


class ClickEvent(BaseModel):
    event_id: str
    session_id: str
    user_id: int | None = None
    event: Literal["search", "view_game", "click_store", "set_alert"]
    game_id: int | None = None
    query: str | None = None
    store: str | None = None
    occurred_at: datetime = Field(default_factory=utcnow)
    served_by: str | None = None
