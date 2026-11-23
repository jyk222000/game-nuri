"""#36 POST /api/events → Kafka clickstream (키 session_id, 형식 messages/clickstream.json)."""

import json
import uuid

import pytest
import redis
from app.core.keys import SESSION_COOKIE_NAME
from app.main import app
from app.services import events as events_service
from app.services import session_store
from confluent_kafka import KafkaException
from fastapi.testclient import TestClient

CONTRACT_FIELDS = {
    "event_id",
    "session_id",
    "user_id",
    "event",
    "game_id",
    "query",
    "store",
    "occurred_at",
    "served_by",
}


class FakeProducer:
    def __init__(self) -> None:
        self.sent: list[dict] = []
        self.polled = 0

    def produce(self, topic, key=None, value=None, on_delivery=None):  # noqa: ANN001
        self.sent.append({"topic": topic, "key": key, "value": json.loads(value)})

    def poll(self, timeout):  # noqa: ANN001
        self.polled += 1


class BrokenProducer:
    def __init__(self, exc: Exception) -> None:
        self.exc = exc

    def produce(self, *args, **kwargs):  # noqa: ANN002, ANN003
        raise self.exc

    def poll(self, timeout):  # noqa: ANN001
        pass


@pytest.fixture
def client(monkeypatch):
    app.dependency_overrides.clear()
    producer = FakeProducer()
    monkeypatch.setattr(events_service, "get_producer", lambda: producer)
    return TestClient(app), producer


def test_search_event_published_with_contract_fields(client) -> None:
    c, producer = client
    sid = str(uuid.uuid4())
    r = c.post(
        "/api/events",
        json={"type": "search", "query": "엘든", "session_id": sid, "at": "2026-11-19T02:30:00Z"},
    )
    assert r.status_code == 200 and r.json() == {"accepted": True}
    sent = producer.sent[0]
    assert sent["topic"] == "clickstream" and sent["key"] == sid
    msg = sent["value"]
    assert set(msg) == CONTRACT_FIELDS
    assert msg["event"] == "search" and msg["query"] == "엘든" and msg["session_id"] == sid
    assert msg["user_id"] is None and msg["game_id"] is None and msg["store"] is None
    assert msg["occurred_at"].endswith("Z") and msg["occurred_at"] != "2026-11-19T02:30:00Z"
    uuid.UUID(msg["event_id"])  # 이벤트마다 새 uuid
    assert producer.polled == 1


def test_other_event_types(client) -> None:
    c, producer = client
    assert c.post("/api/events", json={"type": "view_game", "game_id": 119133}).json()["accepted"]
    assert c.post(
        "/api/events", json={"type": "click_store", "game_id": 119133, "store": "steam"}
    ).json()["accepted"]
    assert c.post("/api/events", json={"type": "set_alert", "game_id": 119133}).json()["accepted"]
    events = [s["value"] for s in producer.sent]
    assert [e["event"] for e in events] == ["view_game", "click_store", "set_alert"]
    assert events[1]["store"] == "steam" and events[1]["game_id"] == 119133


def test_session_id_generated_when_missing_and_event_ids_unique(client) -> None:
    c, producer = client
    c.post("/api/events", json={"type": "view_game", "game_id": 1})
    c.post("/api/events", json={"type": "view_game", "game_id": 1})
    a, b = (s["value"] for s in producer.sent)
    uuid.UUID(a["session_id"])
    assert a["event_id"] != b["event_id"]
    assert producer.sent[0]["key"] == a["session_id"]


def test_logged_in_user_id_recorded_but_session_cookie_never_sent(client, monkeypatch) -> None:
    c, producer = client

    class Valkey:
        def get(self, key):  # noqa: ANN001
            return "7" if key == "session:secret-cookie" else None

    monkeypatch.setattr(session_store, "get_valkey", lambda: Valkey())
    c.cookies.set(SESSION_COOKIE_NAME, "secret-cookie")
    c.post("/api/events", json={"type": "view_game", "game_id": 5})
    msg = producer.sent[0]["value"]
    assert msg["user_id"] == 7
    assert "secret-cookie" not in json.dumps(producer.sent[0])  # 로그인 세션 값은 Kafka로 안 간다


def test_session_id_equal_to_login_cookie_is_replaced(client, monkeypatch) -> None:
    c, producer = client
    cookie = str(uuid.uuid4())

    class Valkey:
        def get(self, key):  # noqa: ANN001
            return "7"

    monkeypatch.setattr(session_store, "get_valkey", lambda: Valkey())
    c.cookies.set(SESSION_COOKIE_NAME, cookie)
    c.post("/api/events", json={"type": "view_game", "game_id": 5, "session_id": cookie})
    sent = producer.sent[0]
    assert cookie not in json.dumps(sent)  # 쿠키 값과 같은 session_id는 새 익명 값으로 바뀐다
    assert sent["key"] == sent["value"]["session_id"]


def test_valkey_down_or_bad_session_is_anonymous_not_error(client, monkeypatch) -> None:
    c, producer = client

    class Dead:
        def get(self, key):  # noqa: ANN001
            raise redis.ConnectionError("down")

    monkeypatch.setattr(session_store, "get_valkey", lambda: Dead())
    c.cookies.set(SESSION_COOKIE_NAME, "whatever")
    r = c.post("/api/events", json={"type": "view_game", "game_id": 5})
    assert r.status_code == 200 and r.json() == {"accepted": True}
    assert producer.sent[0]["value"]["user_id"] is None


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"type": "unknown"},
        {"type": "search"},
        {"type": "search", "query": ""},
        {"type": "search", "query": "x" * 201},
        {"type": "view_game"},
        {"type": "view_game", "game_id": 0},
        {"type": "click_store", "game_id": 1},
        {"type": "set_alert", "game_id": "abc"},
        {"type": "search", "query": "a", "session_id": "not-a-uuid"},
    ],
)
def test_invalid_events_are_422_and_not_sent(client, body) -> None:
    c, producer = client
    r = c.post("/api/events", json=body)
    assert r.status_code == 422 and r.json()["error"]["code"] == "INVALID_REQUEST"
    assert producer.sent == []


@pytest.mark.parametrize("exc", [BufferError("full"), KafkaException("down")])
def test_kafka_failure_is_200_accepted_false(monkeypatch, exc) -> None:
    app.dependency_overrides.clear()
    monkeypatch.setattr(events_service, "get_producer", lambda: BrokenProducer(exc))
    r = TestClient(app).post("/api/events", json={"type": "view_game", "game_id": 1})
    assert r.status_code == 200 and r.json() == {"accepted": False}


def test_served_by_comes_from_server_name(client, monkeypatch) -> None:
    c, producer = client
    from gamenuri_common.config import get_settings

    monkeypatch.setenv("SERVER_NAME", "backend2")
    get_settings.cache_clear()
    try:
        c.post("/api/events", json={"type": "view_game", "game_id": 1})
    finally:
        monkeypatch.delenv("SERVER_NAME")
        get_settings.cache_clear()
    assert producer.sent[0]["value"]["served_by"] == "backend2"
