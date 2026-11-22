"""시각은 DB에 UTC naive로 저장하고, API 응답에서는 ISO 8601 UTC('Z')로 내보낸다."""

from datetime import UTC, datetime
from typing import Annotated

from pydantic import PlainSerializer


def to_utc_iso(value: datetime) -> str:
    """2026-11-19T02:30:00Z. naive는 UTC로 간주하고, tz가 있으면 UTC로 변환한다."""
    if value.tzinfo is not None:
        value = value.astimezone(UTC)
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


# 응답 모델 필드 타입으로 쓴다: created_at: UtcDatetime
UtcDatetime = Annotated[datetime, PlainSerializer(to_utc_iso, return_type=str, when_used="json")]
