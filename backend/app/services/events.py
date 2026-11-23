"""클릭스트림 이벤트를 Kafka `clickstream` 토픽으로 보낸다(#36).

- Backend는 DB에 쓰지 않는다. 이 데이터는 Kafka → ES Sink로 간다 (검색 로그·실시간 검색어).
- 메시지 키 = session_id (같은 세션의 이벤트가 같은 파티션에 순서대로 쌓인다).
- 로그인 세션 쿠키 값은 Kafka로 보내지 않는다.
  session_id는 브라우저가 만든 익명 id(없으면 서버가 생성)다.
- Kafka가 안 되면 화면을 막지 않는다: 200 + accepted=false. 검색어 등 내용은 로그에 안 남긴다.
"""

import logging
import uuid
from datetime import UTC, datetime

from confluent_kafka import KafkaException
from gamenuri_common.config import get_settings
from gamenuri_common.messages import TOPIC_CLICKSTREAM

from app.clients.kafka import get_producer
from app.core.timeutil import to_utc_iso
from app.schemas.events import ClickstreamMessage, EventIn

log = logging.getLogger(__name__)


def _on_delivery(err, _msg) -> None:  # noqa: ANN001
    if err is not None:  # 내용(검색어 등)은 남기지 않고 오류 종류만
        log.warning("clickstream 전달 실패: %s", err.name())


def anonymous_session_id(event: EventIn, login_cookie: str | None) -> str:
    """Kafka의 session_id: 브라우저의 익명 id. 로그인 쿠키 값과 같으면 버리고 새로 만든다."""
    requested = str(event.session_id) if event.session_id else None
    if requested and requested != login_cookie:
        return requested
    return str(uuid.uuid4())


def build_message(
    event: EventIn,
    user_id: int | None,
    now: datetime | None = None,
    login_cookie: str | None = None,
) -> ClickstreamMessage:
    return ClickstreamMessage(
        event_id=str(uuid.uuid4()),
        session_id=anonymous_session_id(event, login_cookie),
        user_id=user_id,
        event=event.type,
        game_id=event.game_id,
        query=event.query,
        store=event.store,
        occurred_at=to_utc_iso(now or datetime.now(UTC)),
        served_by=get_settings().server_name,
    )


def publish(event: EventIn, user_id: int | None, login_cookie: str | None = None) -> bool:
    """Kafka 발행 큐에 넣었으면 True. 큐에 못 넣으면 False (전달 결과는 콜백이 로그로만 남긴다)."""
    message = build_message(event, user_id, login_cookie=login_cookie)
    try:
        producer = get_producer()
        producer.produce(
            TOPIC_CLICKSTREAM,
            key=message.session_id,
            value=message.model_dump_json(),
            on_delivery=_on_delivery,
        )
        producer.poll(0)  # 끝난 전달 콜백을 처리한다 (기다리지 않는다)
    except (BufferError, KafkaException, ValueError) as exc:
        log.warning("clickstream 발행 실패: %s", type(exc).__name__)
        return False
    return True
