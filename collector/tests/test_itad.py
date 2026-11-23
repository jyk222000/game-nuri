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
        self.calls.append({"method": "POST", "url": url, **kw})
        return self.responses.pop(0)

    def get(self, url: str, **kw: Any) -> FakeResp:
        self.calls.append({"method": "GET", "url": url, **kw})
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


# ---- 가격 이력 (kind=price_history)
def hist_item(ts: str, shop_id: int = 61, amount: float = 29.99, cur: str = "USD") -> dict:
    return {
        "timestamp": ts,
        "shop": {"id": shop_id, "name": "Steam"},
        "deal": {
            "price": {"amount": amount, "amountInt": int(amount * 100), "currency": cur},
            "regular": {"amount": 59.99, "amountInt": 5999, "currency": cur},
            "cut": 50,
        },
    }


def test_history_payload_matches_contract() -> None:
    items = [hist_item("2022-10-02T05:10:46+02:00"), hist_item("2022-11-01T10:00:00+01:00", 20)]
    c, s, _ = make_client([FakeResp(200, items)])
    out = list(itad.collect_history([Target("uuid-1", 1245620)], client=c))
    assert len(out) == 1
    key, env = out[0]
    assert key == "uuid-1"
    assert (env.source, env.kind) == ("itad", "price_history")
    assert env.payload == {"id": "uuid-1", "history": items}  # 응답 항목 그대로
    assert env.request["params"]["id"] == "uuid-1"
    assert env.request["params"]["appid"] == "1245620"  # 계약 예시처럼 문자열
    assert "key" not in env.request["params"]
    call = s.calls[0]
    assert call["method"] == "GET"
    assert call["url"].endswith("/games/history/v2")
    assert call["params"]["id"] == "uuid-1"
    assert call["params"]["country"] == "KR"
    assert call["params"]["since"] == itad.HISTORY_FULL_SINCE  # 없으면 최근 3개월만 온다


def test_history_since_is_passed_through() -> None:
    c, s, _ = make_client([FakeResp(200, [hist_item("2026-11-20T00:00:00+01:00")])])
    list(itad.collect_history([Target("u", None)], client=c, since="2026-11-10T00:00:00Z"))
    assert s.calls[0]["params"]["since"] == "2026-11-10T00:00:00Z"


def test_history_without_appid_omits_it() -> None:
    c, _, _ = make_client([FakeResp(200, [hist_item("2026-11-20T00:00:00+01:00")])])
    [(_, env)] = list(itad.collect_history([Target("u", None)], client=c))
    assert "appid" not in env.request["params"]


def test_history_empty_and_failed_games_are_skipped() -> None:
    ok = [hist_item("2026-11-20T00:00:00+01:00")]
    c, _, _ = make_client([FakeResp(200, []), FakeResp(403), FakeResp(200, ok)])
    out = list(itad.collect_history([Target("a", 1), Target("b", 2), Target("c", 3)], client=c))
    assert [k for k, _ in out] == ["c"]  # 한 게임이 실패해도 계속한다


def test_history_is_split_when_too_big() -> None:
    items = [hist_item(f"2022-01-{d:02d}T00:00:00+01:00") for d in range(1, 11)]
    one = len(__import__("json").dumps(items[0], ensure_ascii=False).encode()) + 1
    c, _, _ = make_client([FakeResp(200, items)])
    out = list(itad.collect_history([Target("u", 1)], client=c, max_bytes=one * 4))
    sizes = [len(e.payload["history"]) for _, e in out]
    assert sizes == [4, 4, 2]  # 순서 유지, 같은 모양으로 나눔
    assert all(e.payload["id"] == "u" for _, e in out)
    assert [i for _, e in out for i in e.payload["history"]] == items


def test_split_never_returns_empty_chunk_for_huge_item() -> None:
    items = [hist_item("2022-01-01T00:00:00+01:00")]
    assert [len(c) for c in itad.split_history(items, max_bytes=1)] == [1]


def test_since_from_days() -> None:
    from datetime import UTC, datetime

    assert itad.since_from_days(None) == itad.HISTORY_FULL_SINCE
    now = datetime(2026, 11, 23, 12, 0, 0, tzinfo=UTC)
    assert itad.since_from_days(14, now) == "2026-11-09T12:00:00Z"


def test_history_error_message_never_contains_key() -> None:
    c, _, _ = make_client([FakeResp(403)])
    with pytest.raises(ItadError) as e:
        c.get("/games/history/v2", {"id": "x"})
    assert "SECRETKEY" not in str(e.value)
