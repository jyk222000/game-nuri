"""Kafka 전송 결과 확인 시험. 실제 Kafka 없이 가짜 Producer로 돌린다."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from gamenuri_common.messages import RawEnvelope

from collector import main, producer


class FakeMsg:
    def __init__(self, topic: str) -> None:
        self._topic = topic

    def topic(self) -> str:
        return self._topic


class FakeProducer:
    """produce 때 콜백을 쌓아 두었다가 poll/flush 때 결과를 알려준다."""

    def __init__(
        self,
        fail_delivery: int = 0,
        stuck_on_flush: int = 0,
        buffer_full_times: int = 0,
        produce_error: Exception | None = None,
    ) -> None:
        self.fail_delivery = fail_delivery
        self.stuck_on_flush = stuck_on_flush
        self.buffer_full_times = buffer_full_times
        self.produce_error = produce_error
        self.pending: list[tuple[str, Any]] = []
        self.produced = 0
        self.polls: list[float] = []
        self.flush_timeouts: list[float] = []

    def produce(self, topic: str, key: bytes, value: bytes, on_delivery: Any) -> None:
        if self.produce_error:
            raise self.produce_error
        if self.buffer_full_times > 0:
            self.buffer_full_times -= 1
            raise BufferError("queue full")
        self.produced += 1
        self.pending.append((topic, on_delivery))

    def _deliver(self) -> None:
        for topic, cb in self.pending:
            if self.fail_delivery > 0:
                self.fail_delivery -= 1
                cb("BROKER_DOWN", FakeMsg(topic))
            else:
                cb(None, FakeMsg(topic))
        self.pending = []

    def poll(self, timeout: float = 0) -> int:
        self.polls.append(timeout)
        return 0

    def flush(self, timeout: float) -> int:
        self.flush_timeouts.append(timeout)
        self._deliver()
        return self.stuck_on_flush


@pytest.fixture(autouse=True)
def reset_producer(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(producer, "_producer", None)
    producer._stats.update(ok=0, failed=0)
    producer._logged_errors = 0
    producer._seen_broker_errors.clear()
    yield
    monkeypatch.setattr(producer, "_producer", None)


def install(monkeypatch: pytest.MonkeyPatch, fake: FakeProducer) -> FakeProducer:
    monkeypatch.setattr(producer, "_producer", fake)
    return fake


def env(n: int = 0) -> RawEnvelope:
    return RawEnvelope(source="igdb", kind="game_info", payload={"id": n})


def send(count: int) -> None:
    for i in range(count):
        producer.publish(env(i), str(i))


def test_all_delivered(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = install(monkeypatch, FakeProducer())
    send(3)
    assert producer.flush() == {"ok": 3, "failed": 0}
    assert fake.produced == 3


def test_delivery_failure_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    install(monkeypatch, FakeProducer(fail_delivery=2))
    send(5)
    with pytest.raises(producer.DeliveryError, match="2건"):
        producer.flush()


def test_all_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    install(monkeypatch, FakeProducer(fail_delivery=99))
    send(4)
    with pytest.raises(producer.DeliveryError, match="4건"):
        producer.flush()


def test_unsent_after_flush_timeout_counts_as_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = install(monkeypatch, FakeProducer(stuck_on_flush=7))
    send(2)
    with pytest.raises(producer.DeliveryError):
        producer.flush()
    assert fake.flush_timeouts == [producer.FLUSH_TIMEOUT_SEC]


def test_queue_full_is_drained_and_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = install(monkeypatch, FakeProducer(buffer_full_times=2))
    send(1)
    assert producer.flush() == {"ok": 1, "failed": 0}
    assert fake.polls.count(1) == 2  # 가득 찰 때마다 비우고 다시 시도


def test_queue_stays_full_counts_as_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    install(monkeypatch, FakeProducer(buffer_full_times=999))
    send(1)
    with pytest.raises(producer.DeliveryError, match="1건"):
        producer.flush()


def test_local_produce_error_does_not_stop_the_rest(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = install(monkeypatch, FakeProducer(produce_error=ValueError("too large")))
    send(2)  # 예외가 밖으로 나오지 않는다
    fake.produce_error = None
    send(1)
    with pytest.raises(producer.DeliveryError, match="2건"):
        producer.flush()


def test_flush_without_producer_is_noop() -> None:  # --dry-run
    assert producer.flush() == {"ok": 0, "failed": 0}


def test_counters_reset_after_flush(monkeypatch: pytest.MonkeyPatch) -> None:
    install(monkeypatch, FakeProducer(fail_delivery=1))
    send(1)
    with pytest.raises(producer.DeliveryError):
        producer.flush()
    send(2)
    assert producer.flush() == {"ok": 2, "failed": 0}


def test_failure_log_does_not_contain_payload(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    install(monkeypatch, FakeProducer(fail_delivery=1))
    producer.publish(
        RawEnvelope(source="igdb", kind="game_info", payload={"secret": "SHOULD_NOT_LOG"}), "1"
    )
    with caplog.at_level("ERROR"), pytest.raises(producer.DeliveryError):
        producer.flush()
    assert "SHOULD_NOT_LOG" not in caplog.text
    assert "raw.igdb" in caplog.text


def test_only_first_failures_are_logged(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    install(monkeypatch, FakeProducer(fail_delivery=99))
    send(20)
    with caplog.at_level("ERROR"), pytest.raises(producer.DeliveryError):
        producer.flush()
    detail = [r for r in caplog.records if "Kafka 전송 실패 topic" in r.message]
    assert len(detail) == producer.MAX_LOGGED_ERRORS


def test_broker_error_logged_once(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level("WARNING"):
        producer._on_error("all brokers down")
        producer._on_error("all brokers down")
    assert len([r for r in caplog.records if "클라이언트 오류" in r.message]) == 1


# ---- main._publish_all
def test_publish_all_raises_on_delivery_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    install(monkeypatch, FakeProducer(fail_delivery=1))
    with pytest.raises(producer.DeliveryError):
        main._publish_all([("1", env(1)), ("2", env(2))], dry_run=False)


def test_publish_all_does_not_hide_collect_error(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = install(monkeypatch, FakeProducer(fail_delivery=1))

    def items() -> Iterator[tuple[str, RawEnvelope]]:
        yield "1", env(1)
        raise RuntimeError("수집 중 오류")

    with pytest.raises(RuntimeError, match="수집 중 오류"):
        main._publish_all(items(), dry_run=False)
    assert fake.flush_timeouts  # 이미 낸 것은 비웠다


def test_main_exits_1_on_delivery_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(args: Any) -> int:
        raise producer.DeliveryError("x")

    monkeypatch.setitem(main.RUNNERS, "igdb", boom)
    monkeypatch.setattr("sys.argv", ["collector", "--source", "igdb"])
    with pytest.raises(SystemExit) as e:
        main.main()
    assert e.value.code == 1
