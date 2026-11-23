"""클릭스트림 이벤트: 요청 본문(api.md #36)과 Kafka 메시지(messages/clickstream.json)."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

EventType = Literal["search", "view_game", "click_store", "set_alert"]


class EventIn(BaseModel):
    """api.md 본문 `{ "type": "search", "query": "...", "at": "...Z", ... }`.

    `at`(브라우저 시각)은 받지만 쓰지 않는다: 시각은 서버 시각(UTC)으로 기록한다.
    """

    type: EventType
    game_id: int | None = Field(default=None, gt=0)
    query: str | None = Field(default=None, min_length=1, max_length=200)
    store: str | None = Field(default=None, min_length=1, max_length=32)
    session_id: UUID | None = None  # 브라우저가 만든 익명 세션 id. 없으면 서버가 만든다
    at: str | None = Field(default=None, max_length=40)

    @model_validator(mode="after")
    def _required_by_type(self) -> "EventIn":
        if self.type == "search" and not self.query:
            raise ValueError("search에는 query가 필요합니다")
        if self.type != "search" and self.game_id is None:
            raise ValueError(f"{self.type}에는 game_id가 필요합니다")
        if self.type == "click_store" and not self.store:
            raise ValueError("click_store에는 store가 필요합니다")
        return self


class EventAccepted(BaseModel):
    accepted: bool


class ClickstreamMessage(BaseModel):
    """Kafka `clickstream` 메시지 (키 = session_id)."""

    event_id: str
    session_id: str
    user_id: int | None
    event: EventType
    game_id: int | None
    query: str | None
    store: str | None
    occurred_at: str  # UTC ISO 8601 'Z'
    served_by: str
