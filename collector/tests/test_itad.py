"""ITAD 수집기 시험. 네트워크 없이 가짜 세션으로 돌린다."""

from __future__ import annotations

from typing import Any

import pytest
from collector.sources import itad
from collector.sources.itad import ItadClient, ItadError, Target


class FakeResp:
    def __init__(self, status: int = 200, data: Any = None, headers: dict | None = None) -> None:
        self.status_code = status
        self._data = data
        self.headers = headers or {}

    @property
    def ok(self) -> bool:
        return self.status_code < 400

    def json(self) -> Any:
        return self._data


class FakeSession:
    def __init__(self, responses: list[FakeResp]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def post(self, url: str, **kw: Any) -> FakeResp:
        self.calls.append({"url": url, **kw})
        return self.responses.pop(0)


def make_client(responses: list[FakeResp]) -> tuple[ItadClient, FakeSession, list[float]]:
    sleeps: list[float] = []
    s = FakeSession(responses)
    c = ItadClient("SECRETKEY", session=s, sleep=sleeps.append, clock=lambda: 0.0)  # type: ignore[arg-type]
    return c, s, sleeps


def test_collect_keeps_payload_and_adds_steam_hint() -> None:
    row = {"id": "uuid-1", "historyLow": {}, "deals": [{"shop": {"id": 61}, "cut": 10}]}
    c, s, _ = make_client([FakeResp(200, [row])])
    out = list(itad.collect([Target("uuid-1", 1091500), Target("uuid-2", None)], client=c))
    assert len(out) == 1
    key, env = out[0]
    assert key == "uuid-1"
    assert (env.source, env.kind) == ("itad", "price")
    assert env.payload == row  # 가공 없음
    assert env.request["params"] == {"country": "KR", "steam_appid": 1091500}
    assert "key" not in env.request["params"]  # 키는 봉투에 넣지 않는다
    assert s.calls[0]["json"] == ["uuid-1", "uuid-2"]
    assert s.calls[0]["params"]["country"] == "KR"


def test_batches_by_size(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(itad, "BATCH_SIZE", 2)
    c, s, _ = make_client([FakeResp(200, [])] * 2)
    list(itad.collect([Target(f"u{i}", None) for i in range(3)], client=c))
    assert [len(call["json"]) for call in s.calls] == [2, 1]


def test_retry_on_429_uses_retry_after() -> None:
    c, _, sleeps = make_client([FakeResp(429, headers={"Retry-After": "7"}), FakeResp(200, [])])
    assert c.post("/x", {}, []) == []
    assert 7.0 in sleeps


def test_retry_gives_up() -> None:
    c, s, _ = make_client([FakeResp(503)] * (itad.MAX_RETRIES + 1))
    with pytest.raises(ItadError):
        c.post("/x", {}, [])
    assert len(s.calls) == itad.MAX_RETRIES + 1


def test_error_message_never_contains_key() -> None:
    c, _, _ = make_client([FakeResp(403)])
    with pytest.raises(ItadError) as e:
        c.post("/games/prices/v3", {}, [])
    assert "SECRETKEY" not in str(e.value)


def test_rate_limit_enforced() -> None:
    c, _, sleeps = make_client([FakeResp(200, [])] * 2)
    c.post("/x", {}, [])
    c.post("/x", {}, [])
    assert any(abs(w - itad.MIN_INTERVAL_SEC) < 1e-9 for w in sleeps)


def test_missing_key() -> None:
    with pytest.raises(ItadError):
        ItadClient("")


def test_load_targets_from_real_list() -> None:
    targets = itad.load_targets()
    assert len(targets) > 900  # itad_id 없는 게임은 건너뛴다
    assert targets[0] == Target("018d937f-2997-7131-b8b9-7c8af4825fa8", 1091500)
    assert itad.load_targets(limit=3) == targets[:3]
