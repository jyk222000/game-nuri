"""클릭스트림 수집 라우터(#36). 로그인 없이 호출한다 (로그인했으면 user_id를 함께 기록)."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import get_optional_user_id
from app.schemas.events import EventAccepted, EventIn
from app.services import events

router = APIRouter(prefix="/api")


@router.post("/events", response_model=EventAccepted)
def post_event(
    body: EventIn, user_id: Annotated[int | None, Depends(get_optional_user_id)]
) -> EventAccepted:
    return EventAccepted(accepted=events.publish(body, user_id))
