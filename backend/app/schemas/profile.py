"""내 정보(#3), Steam 연동(#4), 내 PC 사양(#30), 게임 사양(#29) 요청·응답 모양."""

from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

from app.core.timeutil import UtcDatetime

Nickname = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]


class MeOut(BaseModel):
    user_id: int
    email: str
    name: str | None  # users.nickname. picture는 응답에서 뺀다 (api.md)
    steam_id: str | None


class MePatch(BaseModel):
    name: Nickname


class SteamBody(BaseModel):
    # 17자리 숫자가 아니면 400 INVALID_STEAM_ID(업무 규칙)라서 여기서는 문자열인지만 본다.
    steam_id: str


class SteamOut(BaseModel):
    steam_id: str


class SpecsBody(BaseModel):
    cpu: str | None = Field(default=None, max_length=128)
    gpu: str | None = Field(default=None, max_length=128)
    ram_gb: int | None = Field(default=None, gt=0, le=4096)
    os: str | None = Field(default=None, max_length=64)


class SpecsOut(BaseModel):
    cpu: str  # 미입력이면 ""
    gpu: str
    ram_gb: int | None
    os: str


class RequirementsOut(BaseModel):
    game_id: int
    minimum_text: str | None
    recommended_text: str | None
    updated_at: UtcDatetime | None  # 사양 정보가 없으면 null
