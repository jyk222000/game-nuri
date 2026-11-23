"""Steam 수집기 시험. 네트워크 없이 가짜 세션으로 돌린다."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from collector.sources import steam
from collector.sources.steam import ReviewState, SteamClient, SteamError


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

    def get(self, url: str, **kw: Any) -> FakeResp:
        self.calls.append({"url": url, **kw})
        return self.responses.pop(0)


def make_client(responses: list[FakeResp]) -> tuple[SteamClient, FakeSession, list[float]]:
    sleeps: list[float] = []
    s = FakeSession(responses)
    return SteamClient(session=s, sleep=sleeps.append, clock=lambda: 0.0), s, sleeps  # type: ignore[arg-type]


def review(rid: int, created: int) -> dict[str, Any]:
    return {"recommendationid": str(rid), "timestamp_created": created, "review": "좋다"}


def page(reviews: list[dict], cursor: str = "c") -> FakeResp:
    return FakeResp(200, {"response": {"reviews": reviews, "cursor": cursor}})


# ---- app_details / player_count
def test_app_details_keeps_body_and_skips_failures() -> None:
    ok = {"10": {"success": True, "data": {"name": "A"}}}
    bad = {"20": {"success": False}}
    c, s, _ = make_client(
        [FakeResp(200, ok), FakeResp(200, bad), FakeResp(500)] + [FakeResp(500)] * 3
    )
    out = list(steam.collect_app_details([10, 20, 30], client=c))
    assert len(out) == 1
    key, env = out[0]
    assert (key, env.source, env.kind) == ("10", "steam", "app_details")
    assert env.payload == ok  # 가공 없음
    assert env.request["params"]["appid"] == 10
    assert s.calls[0]["params"]["cc"] == "kr"


def test_player_count() -> None:
    body = {"response": {"player_count": 1234, "result": 1}}
    c, _, _ = make_client([FakeResp(200, body)])
    [(key, env)] = list(steam.collect_player_counts([10], client=c))
    assert (key, env.kind, env.payload) == ("10", "player_count", body)
    assert env.request["params"] == {"appid": 10}


# ---- 클라이언트
def test_retry_uses_retry_after_then_gives_up() -> None:
    c, _, sleeps = make_client([FakeResp(429, headers={"Retry-After": "9"}), FakeResp(200, {})])
    assert c.get("players", "http://x", {}) == {}
    assert 9.0 in sleeps
    c2, s2, _ = make_client([FakeResp(503)] * (steam.MAX_RETRIES + 1))
    with pytest.raises(SteamError):
        c2.get("players", "http://x", {})
    assert len(s2.calls) == steam.MAX_RETRIES + 1


def test_throttle_per_kind() -> None:
    c, _, sleeps = make_client([FakeResp(200, {})] * 2)
    c.get("appdetails", "http://x", {})
    c.get("appdetails", "http://x", {})
    assert any(abs(w - steam.LIMITS["appdetails"][0]) < 1e-9 for w in sleeps)


def test_error_has_no_query() -> None:
    c, _, _ = make_client([FakeResp(403)])
    with pytest.raises(SteamError) as e:
        c.get("reviews", "http://x/api?input_json=SECRET", {})
    assert "SECRET" not in str(e.value)


# ---- 리뷰
def test_first_run_collects_pages_until_empty(tmp_path: Path) -> None:
    st = ReviewState(tmp_path / "s.json")
    c, s, _ = make_client(
        [page([review(3, 300), review(2, 200)], "c1"), page([review(1, 100)], "c2"), page([], "c3")]
    )
    out = list(steam.collect_reviews([10], client=c, state=st))
    # 리뷰 1건 = 봉투 1개, 키는 steam_appid
    assert [k for k, _ in out] == ["10", "10", "10"]
    assert [e.payload["recommendationid"] for _, e in out] == ["3", "2", "1"]
    assert out[0][1].payload["steam_appid"] == 10
    assert out[0][1].kind == "review"
    assert st.get(10) == (300, {"3"})
    # 두 번째 요청은 첫 응답의 cursor로 이어간다
    assert json.loads(s.calls[1]["params"]["input_json"])["cursor"] == "c1"
    assert json.loads(s.calls[0]["params"]["input_json"])["languages"] == ["koreana"]


def test_incremental_stops_at_known_review(tmp_path: Path) -> None:
    st = ReviewState(tmp_path / "s.json")
    st.update(10, [review(2, 200)])
    c, s, _ = make_client([page([review(4, 400), review(3, 300), review(2, 200), review(1, 100)])])
    out = list(steam.collect_reviews([10], client=c, state=st))
    assert [e.payload["recommendationid"] for _, e in out] == ["4", "3"]
    assert len(s.calls) == 1  # 아는 리뷰를 만난 페이지에서 멈춤
    assert st.get(10)[0] == 400


def test_nothing_new_sends_nothing(tmp_path: Path) -> None:
    st = ReviewState(tmp_path / "s.json")
    st.update(10, [review(2, 200)])
    c, _, _ = make_client([page([review(2, 200), review(1, 100)])])
    assert list(steam.collect_reviews([10], client=c, state=st)) == []


def test_same_second_new_review_is_kept(tmp_path: Path) -> None:
    st = ReviewState(tmp_path / "s.json")
    st.update(10, [review(2, 200)])
    c, _, _ = make_client([page([review(3, 200), review(2, 200), review(1, 100)])])
    out = list(steam.collect_reviews([10], client=c, state=st))
    assert [e.payload["recommendationid"] for _, e in out] == ["3"]
    assert st.get(10) == (200, {"2", "3"})


def test_max_reviews_caps_first_run(tmp_path: Path) -> None:
    st = ReviewState(tmp_path / "s.json")
    c, s, _ = make_client([page([review(i, 1000 - i) for i in range(100)], "c1")])
    out = list(steam.collect_reviews([10], client=c, state=st, max_reviews=30))
    assert len(out) == 30
    assert len(s.calls) == 1


def test_review_payload_is_the_review_itself(tmp_path: Path) -> None:
    """payload = 리뷰 객체 그대로 + steam_appid. 페이지 단위 필드는 담지 않는다."""
    st = ReviewState(tmp_path / "s.json")
    r = {**review(1, 100), "voted_up": True, "author": {"playtime_forever": 60}}
    resp = FakeResp(
        200,
        {"response": {"reviews": [r], "cursor": "c", "query_summary": {"total_reviews": 9}}},
    )
    c, _, _ = make_client([resp, page([], "c2")])
    [(key, env)] = list(steam.collect_reviews([10], client=c, state=st))
    assert env.payload == {"steam_appid": 10, **r}
    assert "query_summary" not in env.payload and "reviews" not in env.payload
    assert env.request["params"]["appid"] == 10


def test_stops_on_repeated_cursor(tmp_path: Path) -> None:
    st = ReviewState(tmp_path / "s.json")
    c, s, _ = make_client([page([review(2, 200)], "*")])
    list(steam.collect_reviews([10], client=c, state=st))
    assert len(s.calls) == 1


def test_failed_game_does_not_stop_others(tmp_path: Path) -> None:
    st = ReviewState(tmp_path / "s.json")
    c, _, _ = make_client([FakeResp(403), page([review(1, 100)], "c"), page([], "c2")])
    out = list(steam.collect_reviews([10, 20], client=c, state=st))
    assert [k for k, _ in out] == ["20"]
    assert st.get(10) == (0, set())


def test_state_persists(tmp_path: Path) -> None:
    p = tmp_path / "s.json"
    st = ReviewState(p)
    st.update(10, [review(5, 500)])
    assert not p.exists()  # update는 메모리만 바꾼다 (전송 확인 뒤 save)
    st.save()
    assert ReviewState(p).get(10) == (500, {"5"})


def test_load_appids_from_real_list() -> None:
    ids = steam.load_appids()
    assert len(ids) > 900
    assert ids[0] == 1091500
    assert steam.load_appids(limit=3) == ids[:3]
