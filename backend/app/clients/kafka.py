"""Kafka Producer (clickstream 발행용). 연결은 처음 쓸 때 맺는다 (Kafka가 꺼져 있어도 앱은 뜬다).

접속 주소는 KAFKA_BOOTSTRAP 환경 변수(예: kafka1:9092,kafka2:9092,kafka3:9092)에서만 읽는다.
"""

from functools import lru_cache

from confluent_kafka import Producer
from gamenuri_common.config import get_settings

FLUSH_TIMEOUT_SECONDS = 5


@lru_cache
def get_producer() -> Producer:
    s = get_settings()
    return Producer(
        {
            "bootstrap.servers": s.kafka_bootstrap,
            "client.id": f"backend-{s.server_name or 'local'}",
            "acks": "all",  # 복제본까지 기록돼야 성공
            "enable.idempotence": True,  # 재시도해도 같은 메시지가 두 번 쌓이지 않게
            "message.timeout.ms": 5000,  # 5초 안에 못 보내면 포기(사용자 요청을 오래 붙잡지 않는다)
            "socket.timeout.ms": 3000,
        }
    )


def close() -> None:
    """종료할 때 아직 안 나간 메시지를 보낸다. Producer를 쓴 적이 없으면 아무것도 안 한다."""
    if get_producer.cache_info().currsize:
        get_producer().flush(FLUSH_TIMEOUT_SECONDS)
