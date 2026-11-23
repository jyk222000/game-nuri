"""다나와 크롤러 시험. 네트워크 없이 가짜 HTML과 가짜 세션으로 돌린다."""

from __future__ import annotations

from typing import Any

import pytest
from collector.sources import danawa
from collector.sources.danawa import DanawaClient, DanawaError, Query

ROBOTS = "User-agent: *\nCrawl-delay: 10\nDisallow: /api/\nDisallow: /bridge/\n"


def product(
    pcode: str,
    name: str,
    bundle: str | None,
    price: int,
    shops: int,
    cats: tuple[str, ...] = ("게임", "콘솔게임", "PS5-SW"),
) -> str:
    cat = ",".join(f'"{c}"' for c in cats)
    b = f'"bundleName":"{bundle}",' if bundle else ""
    return (
        f'{{"productSeq":"{pcode}","productName":"{name}",{b}"minPrice":{price},'
        f'"shopCount":{shops},"categoryNameList":[{cat}]}},'
    )


def html_of(*parts: str) -> str:
    return "<html>" + "".join(parts) + "</html>"


class FakeResp:
    def __init__(self, status: int = 200, text: str = "", headers: dict | None = None) -> None:
        self.status_code = status
        self.text = text
        self.headers = headers or {}

    @property
    def ok(self) -> bool:
        return self.status_code < 400


class FakeSession:
    def __init__(self, searches: list[FakeResp], robots: str = ROBOTS) -> None:
        self.searches = list(searches)
        self.robots = robots
        self.search_params: list[dict] = []

    def get(self, url: str, **kw: Any) -> FakeResp:
        if url.endswith("/robots.txt"):
            return FakeResp(200, self.robots)
        self.search_params.append(kw["params"])
        return self.searches.pop(0)


def make_client(searches: list[FakeResp], robots: str = ROBOTS):
    sleeps: list[float] = []
    s = FakeSession(searches, robots)
    c = DanawaClient(session=s, sleep=sleeps.append, clock=lambda: 0.0)  # type: ignore[arg-type]
    return c, s, sleeps


def test_parse_and_payload_fields() -> None:
    h = html_of(
        product("111", "CD프로젝트 레드 사이버펑크 2077 한국어", "PS5, 패키지디스크", 42800, 20),
        product("222", "사이버펑크 2077", "PS4, 중고/패키지디스크", 12900, 8, ("게임", "콘솔게임")),
        product("333", "사이버펑크 2077 PC", "PC, GOG코드", 43410, 12, ("게임", "PC게임")),
        product("444", "스위치2 사이버펑크", "SWITCH2, 패키지칩", 81800, 33),
    )
    items = {i["pcode"]: danawa.to_payload(i) for i in danawa.parse_catalog(h)}
    assert items["111"]["platform_hint"] == "PS5"
    assert items["111"]["edition"] == "physical"
    assert items["111"]["condition"] == "new"
    assert items["111"]["lowest_price"] == 42800
    assert items["111"]["shop_count"] == 20
    assert items["111"]["url"] == "https://prod.danawa.com/info/?pcode=111"
    assert items["222"]["condition"] == "used"
    assert items["333"]["edition"] == "code"
    assert items["333"]["medium"] == "code"
    assert items["444"]["platform_hint"] == "Switch2"  # Switch2가 Switch보다 먼저
    assert items["444"]["medium"] == "cartridge"


def test_parse_unescapes_embedded_json() -> None:
    raw = (
        '\\"productSeq\\":\\"555\\",\\"productName\\":\\"아&amp;b <b>게임</b>\\",'
        '\\"minPrice\\":1000'
    )
    [it] = danawa.parse_catalog(raw)
    assert it["title"] == "아&b 게임"
    assert it["min_price"] == 1000


def test_shop_listings_are_not_parsed_as_catalog() -> None:
    h = html_of(
        '{"productSeq":"TH201_97664017","productName":"위쳐3 중고","minPrice":81780},',
        product("666", "위쳐 3", "Switch, 패키지칩", 187000, 5),
    )
    assert [i["pcode"] for i in danawa.parse_catalog(h)] == ["666"]


def test_group_variant_inherits_category_and_name() -> None:
    h = html_of(
        product("10", "엘든 링", None, 50000, 5),
        '{"productSeq":"11","minPrice":30000,"shopCount":3},',
        '"wishListBundleVal":"PS5^10**PS4, 중고/패키지디스크^11//엘든 링 그룹",',
    )
    by = {i["pcode"]: i for i in danawa.parse_catalog(h)}
    assert by["11"]["category"] == ["게임", "콘솔게임", "PS5-SW"]
    assert by["11"]["bundle"] == "PS4, 중고/패키지디스크"
    assert by["11"]["title"] == "엘든 링 그룹"


def test_collect_filters_non_game_no_price_and_dupes() -> None:
    page = html_of(
        product("1", "게임 A", "PS5, 패키지디스크", 10000, 3),
        product("2", "게임패드", None, 50000, 3, ("게임주변기기",)),
        product("3", "게임 B", "PS5, 패키지디스크", 0, 0),
    )
    page2 = html_of(product("1", "게임 A", "PS5, 패키지디스크", 10000, 3))
    c, s, _ = make_client([FakeResp(200, page), FakeResp(200, page2)])
    out = list(danawa.collect([Query(7, "게임"), Query(8, "게임 A")], client=c))
    assert [k for k, _ in out] == ["1"]  # 비게임·가격 없음·중복은 보내지 않는다
    key, env = out[0]
    assert (env.source, env.kind) == ("danawa", "console_price")
    assert env.request["params"] == {"query": "게임", "igdb_id": 7}
    assert env.payload["pcode"] == "1"
    assert s.search_params == [{"query": "게임"}, {"query": "게임 A"}]


def test_one_failure_does_not_stop_others() -> None:
    page = html_of(product("1", "게임 A", "PS5, 패키지디스크", 10000, 3))
    c, _, _ = make_client([FakeResp(403), FakeResp(200, page)])
    out = list(danawa.collect([Query(1, "a"), Query(2, "b")], client=c))
    assert [k for k, _ in out] == ["1"]


def test_empty_page_warns_and_continues(caplog: pytest.LogCaptureFixture) -> None:
    c, _, _ = make_client([FakeResp(200, "<html>없음</html>")])
    with caplog.at_level("WARNING"):
        assert list(danawa.collect([Query(1, "a")], client=c)) == []
    assert any("0건" in r.message for r in caplog.records)


def test_interval_is_robots_crawl_delay_or_more() -> None:
    c, _, _ = make_client([], robots="User-agent: *\nCrawl-delay: 25\n")
    assert c.interval == 25.0
    c2, _, _ = make_client([])
    assert c2.interval == danawa.MIN_INTERVAL_SEC


def test_throttle_between_searches() -> None:
    c, _, sleeps = make_client([FakeResp(200, ""), FakeResp(200, "")])
    c.search("a")
    c.search("b")
    assert any(abs(w - 10.0) < 1e-9 for w in sleeps)


def test_robots_blocked_path_is_not_fetched() -> None:
    c, s, _ = make_client([], robots="User-agent: *\nDisallow: /dsearch.php\n")
    with pytest.raises(DanawaError):
        c.search("a")
    assert s.search_params == []


def test_retry_then_ok_and_give_up() -> None:
    c, _, sleeps = make_client([FakeResp(429, headers={"Retry-After": "7"}), FakeResp(200, "ok")])
    assert c.search("a") == "ok"
    assert 7.0 in sleeps
    c2, _, _ = make_client([FakeResp(503)] * (danawa.MAX_RETRIES + 1))
    with pytest.raises(DanawaError):
        c2.search("a")


def test_user_agent_has_project_name() -> None:
    assert "game-nuri" in danawa.USER_AGENT


def test_load_queries_only_console_games() -> None:
    qs = danawa.load_queries()
    assert 700 < len(qs) < 900
    assert qs[0] == Query(1877, "사이버펑크 2077")
    assert danawa.load_queries(limit=3) == qs[:3]
