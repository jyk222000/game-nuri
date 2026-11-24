"""Kafka로 보내는 곳은 여기 하나뿐이다.

`produce()`는 메시지를 대기열에 넣고 바로 돌아오고 실제 전송은 뒤에서 일어난다.
그래서 실패(주소 오류, 토픽 없음, 권한 없음)는 전달 결과 콜백으로만 알 수 있다.
여기서 성공·실패를 세고, `flush()`가 끝에서 실패가 하나라도 있으면 `DeliveryError`를
올려 "수집 완료"로 오해하지 않게 한다.
"""

import json
from pathlib import Path
from typing import Any

from gamenuri_common.config import get_settings
from gamenuri_common.logging import get_logger
from gamenuri_common.messages import TOPIC_RAW, RawEnvelope

log = get_logger("collector.producer")

FLUSH_TIMEOUT_SEC = 60  # 끝에서 대기열이 비기를 기다리는 시간
MESSAGE_TIMEOUT_MS = 60_000  # Kafka에 닿지 않을 때 한 메시지를 포기하기까지 (기본 5분은 너무 길다)
QUEUE_FULL_RETRIES = 5  # 대기열이 가득 차면 비우고 다시 시도하는 횟수
MAX_LOGGED_ERRORS = 5  # 실패 상세는 처음 몇 건만 로그로 남긴다

_producer = None
_sample_count: dict[str, int] = {}
_stats = {"ok": 0, "failed": 0}
_logged_errors = 0
_seen_broker_errors: set[str] = set()


class DeliveryError(RuntimeError):
    """Kafka 전송에 실패한 메시지가 있다."""


def _on_delivery(err: Any, msg: Any) -> None:
    """전달 결과 콜백. 메시지 내용은 로그에 남기지 않는다."""
    global _logged_errors
    if err is None:
        _stats["ok"] += 1
        return
    _stats["failed"] += 1
    if _logged_errors < MAX_LOGGED_ERRORS:
        _logged_errors += 1
        log.error("Kafka 전송 실패 topic=%s: %s", msg.topic(), err)


def _on_error(err: Any) -> None:
    """브로커 연결 같은 클라이언트 수준 오류. 같은 오류는 한 번만 남긴다."""
    # 문구에는 "after 2032ms" 같은 매번 다른 숫자가 있어서 오류 코드로 같은 오류를 가린다
    code = getattr(err, "code", None)
    kind = str(code()) if callable(code) else str(err)
    if kind not in _seen_broker_errors:
        _seen_broker_errors.add(kind)
        log.warning("Kafka 클라이언트 오류: %s", err)


def _get_producer():
    global _producer
    if _producer is None:
        from confluent_kafka import Producer

        _producer = Producer(
            {
                "bootstrap.servers": get_settings().kafka_bootstrap,
                "acks": "all",
                "message.timeout.ms": MESSAGE_TIMEOUT_MS,
                "error_cb": _on_error,
            }
        )
    return _producer


def _produce(p: Any, topic: str, key: str, data: str) -> None:
    """대기열이 가득 차면(BufferError) 잠깐 비우고 다시 시도한다. 그래도 안 되면 실패로 센다."""
    for _ in range(QUEUE_FULL_RETRIES):
        try:
            p.produce(topic, key=key.encode(), value=data.encode(), on_delivery=_on_delivery)
            return
        except BufferError:
            p.poll(1)
    _stats["failed"] += 1
    log.error("Kafka 대기열이 계속 가득 차 있어 메시지를 보내지 못했다 topic=%s", topic)


def publish(msg: RawEnvelope, key: str, dry_run: bool = False) -> None:
    topic = TOPIC_RAW[msg.source]
    data = msg.model_dump_json()
    if dry_run:
        # 같은 키로 kind가 다른 메시지(game_info·time_to_beat)가 덮어쓰지 않게 kind를 넣는다
        # 같은 실행에서 같은 키가 또 나오면(리뷰 페이지) 번호를 붙인다
        name = f"{topic}.{msg.kind}.{key}"
        if msg.kind == "review":  # 같은 게임의 리뷰는 키가 같으므로 리뷰 번호로 구분한다
            name += f".{msg.payload.get('recommendationid')}"
        _sample_count[name] = _sample_count.get(name, 0) + 1
        if _sample_count[name] > 1:
            name += f".{_sample_count[name]}"
        out = Path(__file__).resolve().parents[1] / "samples" / f"{name}.json"
        out.parent.mkdir(exist_ok=True)
        out.write_text(json.dumps(json.loads(data), ensure_ascii=False, indent=2), encoding="utf-8")
        return
    p = _get_producer()
    try:
        _produce(p, topic, key, data)
    except Exception as e:  # 한 건의 로컬 오류(예: 메시지가 너무 큼)로 전체를 멈추지 않는다
        _stats["failed"] += 1
        log.error("Kafka produce 오류 topic=%s: %s", topic, e)
    p.poll(0)


def publish_refined(topic: str, key: str, value: dict[str, Any], dry_run: bool = False) -> None:
    """refined.* 토픽으로 보낸다(리뷰 요약 배치처럼 수집기가 아닌 프로그램이 직접 만드는 메시지).

    value는 JDBC Sink용 JSON+schema 형식이어야 한다(docs/contracts/messages 참고).
    """
    data = json.dumps(value, ensure_ascii=False)
    if dry_run:
        out = Path(__file__).resolve().parents[1] / "samples" / f"{topic}.{key}.json"
        out.parent.mkdir(exist_ok=True)
        out.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        return
    p = _get_producer()
    try:
        _produce(p, topic, key, data)
    except Exception as e:  # 한 건의 로컬 오류로 전체를 멈추지 않는다
        _stats["failed"] += 1
        log.error("Kafka produce 오류 topic=%s: %s", topic, e)
    p.poll(0)


def flush(raise_on_failure: bool = True) -> dict[str, int]:
    """대기열이 빌 때까지 기다리고 성공·실패 개수를 남긴다. 실패가 있으면 DeliveryError."""
    global _logged_errors
    if _producer is None:  # --dry-run
        return {"ok": 0, "failed": 0}
    remaining = _producer.flush(FLUSH_TIMEOUT_SEC)
    if remaining:
        _stats["failed"] += remaining
        log.error("%d초 안에 보내지 못한 메시지 %d건", FLUSH_TIMEOUT_SEC, remaining)
    result = dict(_stats)
    _stats["ok"] = _stats["failed"] = 0
    _logged_errors = 0
    if result["failed"]:
        log.error("Kafka 전송 결과: 성공 %d, 실패 %d", result["ok"], result["failed"])
        if raise_on_failure:
            raise DeliveryError(f"Kafka 전송 실패 {result['failed']}건 (성공 {result['ok']}건)")
    else:
        log.info("Kafka 전송 결과: 성공 %d, 실패 0", result["ok"])
    return result
