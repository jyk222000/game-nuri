"""API 응답·요청 모양 (docs/contracts/api.md). DB 모델(app/db/models)과는 따로 둔다."""

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.core.timeutil import UtcDatetime
from app.schemas.game import Card


# ---- 찜 (#17) ----
class WishlistAdd(BaseModel):
    game_id: int = Field(gt=0)


class WishlistState(BaseModel):
    game_id: int
    wished: bool


# ---- 목표가 알림 (#19) ----
class AlertCreate(BaseModel):
    game_id: int = Field(gt=0)
    # 0 이하는 400 INVALID_PRICE(업무 규칙)라서 여기서는 정수인지만 본다.
    target_price_krw: int


class AlertPatch(BaseModel):
    target_price_krw: int | None = None
    active: bool | None = None

    @model_validator(mode="after")
    def _need_one(self) -> "AlertPatch":
        if self.target_price_krw is None and self.active is None:
            raise ValueError("target_price_krw 또는 active가 필요합니다")
        return self


class AlertOut(BaseModel):
    alert_id: int
    game_id: int
    target_price_krw: int
    active: bool
    created_at: UtcDatetime


# ---- 목록 (#18, #20, #21) ----
class WishlistOut(BaseModel):
    items: list[Card]
    total: int


class AlertListItem(BaseModel):
    alert_id: int
    game_id: int
    game_name: str | None
    target_price_krw: int
    current_krw: int | None  # 새 상품 현재 최저가. 가격이 없으면 null
    active: bool
    created_at: UtcDatetime


class AlertListOut(BaseModel):
    items: list[AlertListItem]
    total: int


class AlertLogItem(BaseModel):
    log_id: int
    game_id: int
    game_name: str | None
    price_krw: int
    target_price_krw: int
    store: str
    sent_at: UtcDatetime
    channel: Literal["email"] = "email"  # 메일 발송만 있다


class AlertLogListOut(BaseModel):
    items: list[AlertLogItem]
    total: int


# ---- 메일 수신 설정 (#22) ----
class NotificationBody(BaseModel):
    email_enabled: bool


class NotificationOut(BaseModel):
    email_enabled: bool


# ---- 내 취향 (#24) ----
class TasteGenre(BaseModel):
    genre: str
    pct: int


class RecentGame(BaseModel):
    """최근 플레이한 보유 게임 (Steam 마지막 플레이 시각 기준)."""

    game_id: int
    name: str  # name_ko 우선, 없으면 games.name
    cover_url: str | None
    last_played_at: UtcDatetime
    playtime_hours: int  # 누적 플레이 시간(시간, 반올림)


class TasteOut(BaseModel):
    total_playtime_hours: int
    owned_games: int
    top_genres: list[TasteGenre]
    style: str
    preferred_length: (
        Literal["short", "medium", "long"] | None
    )  # 선호 플레이 길이(데이터 부족이면 null)
    recent_games: list[RecentGame]  # 최근 플레이한 게임(최근 순, 기록이 없으면 빈 목록)
