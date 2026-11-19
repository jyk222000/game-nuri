"""Kafka로 보내는 곳은 여기 하나뿐이다."""

import json
from pathlib import Path

from gamenuri_common.config import get_settings
from gamenuri_common.messages import TOPIC_RAW, RawEnvelope

_producer = None


def _get_producer():
    global _producer
    if _producer is None:
        from confluent_kafka import Producer

        _producer = Producer({"bootstrap.servers": get_settings().kafka_bootstrap, "acks": "all"})
    return _producer


def publish(msg: RawEnvelope, key: str, dry_run: bool = False) -> None:
    topic = TOPIC_RAW[msg.source]
    data = msg.model_dump_json()
    if dry_run:
        out = Path(__file__).resolve().parents[1] / "samples" / f"{topic}.{key}.json"
        out.parent.mkdir(exist_ok=True)
        out.write_text(json.dumps(json.loads(data), ensure_ascii=False, indent=2), encoding="utf-8")
        return
    p = _get_producer()
    p.produce(topic, key=key.encode(), value=data.encode())
    p.poll(0)


def flush() -> None:
    if _producer is not None:
        _producer.flush(10)
