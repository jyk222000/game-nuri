"""IGDB 수집기 시험. 네트워크 없이 가짜 세션으로 돌린다."""

from __future__ import annotations

from typing import Any

import pytest
from collector.sources import igdb
from collector.sources.igdb import IgdbClient, IgdbError


class FakeResp:
    def __init__(self, status: int = 200, data: Any = None) -> None:
        self.status_code = status
        self._data = data
        self.text = ""

    @property
    def ok(self) -> bool:
        return self.status_code < 400

    def json(self) -> Any:
        return self._data


class FakeSession:
    def __init__(self, api: list[FakeResp]) -> None:
        self.api = list(api)
        self.token_calls = 0
        self.api_calls: list[tuple[str, str]] = []

    def post(self, url: str, **kw: Any) -> FakeResp:
        if url == igdb.TOKEN_URL:
            self.token_calls += 1
            return FakeResp(200, {"access_token": f"tok{self.token_calls}"})
        self.api_calls.append((url.rsplit("/", 1)[1], kw["data"].decode()))
        return self.api.pop(0)


def make_client(api: list[FakeResp]) -> tuple[IgdbClient, FakeSession, list[float]]:
    sleeps: list[float] = []
    s = FakeSession(api)
    c = IgdbClient("id", "secret", session=s, sleep=sleeps.append, clock=lambda: 0.0)  # type: ignore[arg-type]
    return c, s, sleeps


def test_collect_keeps_payload_as_is() -> None:
    game = {"id": 119133, "name": "Elden Ring", "genres": [{"id": 12, "name": "RPG"}]}
    ttb = {"id": 1, "game_id": 119133, "hastily": 100, "normally": 200, "count": 3}
    c, s, _ = make_client([FakeResp(200, [game]), FakeResp(200, [ttb])])
    out = list(igdb.collect([119133, 999], client=c))
    assert [(k, e.kind) for k, e in out] == [
        ("119133", "game_info"),
        ("119133", "time_to_beat"),
    ]
    assert out[0][1].payload == game  # 가공 없음
    assert out[1][1].payload == ttb
    assert out[0][1].source == "igdb"
    assert [e for e, _ in s.api_calls] == ["games", "game_time_to_beats"]
    assert "where id = (119133,999)" in s.api_calls[0][1]


def test_batches_by_size(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(igdb, "BATCH_SIZE", 2)
    c, s, _ = make_client([FakeResp(200, [])] * 4)
    list(igdb.collect([1, 2, 3], client=c))
    assert [e for e, _ in s.api_calls] == [
        "games",
        "games",
        "game_time_to_beats",
        "game_time_to_beats",
    ]


def test_retry_on_429_then_ok() -> None:
    c, _, sleeps = make_client([FakeResp(429), FakeResp(200, [{"id": 1}])])
    assert c.query("games", "x") == [{"id": 1}]
    assert 2 in sleeps  # 첫 백오프 2초


def test_retry_gives_up() -> None:
    c, s, _ = make_client([FakeResp(503)] * (igdb.MAX_RETRIES + 1))
    with pytest.raises(IgdbError):
        c.query("games", "x")
    assert len(s.api_calls) == igdb.MAX_RETRIES + 1


def test_401_refreshes_token_once() -> None:
    c, s, _ = make_client([FakeResp(401), FakeResp(200, [])])
    assert c.query("games", "x") == []
    assert s.token_calls == 2


def test_rate_limit_enforced() -> None:
    c, _, sleeps = make_client([FakeResp(200, [])] * 2)
    c.query("games", "x")
    c.query("games", "x")
    assert any(abs(w - igdb.MIN_INTERVAL_SEC) < 1e-9 for w in sleeps)


def test_missing_credentials() -> None:
    with pytest.raises(IgdbError):
        IgdbClient("", "")


def test_load_game_ids_from_real_list() -> None:
    ids = igdb.load_game_ids()
    assert len(ids) == 1000
    assert ids[0] == 1877  # rank 1: Cyberpunk 2077
    assert igdb.load_game_ids(limit=5) == ids[:5]
