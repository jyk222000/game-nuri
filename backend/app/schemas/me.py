"""API 응답·요청 모양 (docs/contracts/api.md). DB 모델(app/db/models)과는 따로 둔다."""

from pydantic import BaseModel, Field, model_validator

from app.core.timeutil import UtcDatetime


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


# ---- 메일 수신 설정 (#22) ----
class NotificationBody(BaseModel):
    email_enabled: bool


class NotificationOut(BaseModel):
    email_enabled: bool
