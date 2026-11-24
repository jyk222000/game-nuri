"""#93 다나와 에디션: 본편이 없는 플랫폼에만 에디션 가격, 검색 게임 힌트 매칭, 플랫폼 보완."""

import json
from pathlib import Path

from refiner.router import Maps, route
from refiner.rules.console import infer_platform
from refiner.rules.danawa_match import edition_label, exclude_reason, hint_match
from refiner.rules.price import REFINED_PRICE_SCHEMA
from refiner.rules.price_change import LastPrices, collect_round

ROOT = Path(__file__).resolve().parents[2]
CYBERPUNK = 1877


def env(
    title, platform, price, condition="new", at="2026-11-23T15:40:00Z", query="사이버펑크 2077"
):
    return {
        "source": "danawa",
        "kind": "console_price",
        "collected_at": at,
        "request": {"params": {"query": query, "igdb_id": CYBERPUNK}},
        "payload": {
            "pcode": f"{platform}-{condition}-{price}",
            "product_name": title,
            "platform_hint": platform,
            "condition": condition,
            "lowest_price": price,
        },
    }


def prices(r):
    return [m[2]["payload"] for m in r["out"] if m[0] == "prices"]


def maps():
    return Maps({"alias": {"사이버펑크 2077": CYBERPUNK}})


def test_edition_label_and_hard_excludes():
    assert edition_label("사이버펑크 2077 얼티밋 에디션 한국어") == "얼티밋 에디션"
    assert edition_label("엘든 링 GOTY 에디션") == "GOTY 에디션"
    assert edition_label("어쌔신 크리드 리미티드 에디션") == "리미티드 에디션"
    assert edition_label("사이버펑크 2077") is None
    # 리마스터(다른 게임)·굿즈 묶음은 에디션이 아니라 그대로 뺀다
    assert exclude_reason("스파이더맨 리마스터") == "리마스터·굿즈 묶음"
    assert edition_label("스파이더맨 리마스터") is None


def test_cyberpunk_ps5_switch2_only_ultimate_are_kept_with_name():
    """이슈 #93 사례: PS5·Switch2는 얼티밋 에디션으로만 팔린다."""
    m = maps()
    out = []
    for title, plat, price, cond in [
        ("사이버펑크 2077 얼티밋 에디션 한국어", "PS5", 42800, "new"),
        ("얼티밋 에디션 한국어 사이버펑크 2077", "PS5", 79900, "used"),
        ("사이버펑크 2077 얼티밋 에디션 한국어", "Switch2", 81800, "new"),
    ]:
        out += prices(route(env(title, plat, price, cond), m))
    got = {(p["platform"], p["item_condition"]): (p["price_krw"], p["variant_name"]) for p in out}
    assert got == {
        ("PS5", "new"): (42800, "얼티밋 에디션"),
        ("PS5", "used"): (79900, "얼티밋 에디션"),
        ("Switch2", "new"): (81800, "얼티밋 에디션"),
    }


def test_base_platform_never_mixes_edition():
    """본편이 있는 플랫폼(PS4)은 에디션 가격이 섞이지 않는다 — 순서와 상관없이."""
    m = maps()
    base = prices(route(env("사이버펑크 2077 한국어", "PS4", 25000), m))
    assert base[0]["variant_name"] is None
    r = route(env("사이버펑크 2077 얼티밋 에디션", "PS4", 19000), m)  # 더 싸도
    assert prices(r) == [] and r["unmatched"][0]["reason"] == "에디션 (본편 있음)"
    # 다음 회차에도 그대로
    r = route(env("사이버펑크 2077 얼티밋 에디션", "PS4", 18000, at="2026-11-23T21:40:00Z"), m)
    assert prices(r) == []

    # 에디션이 먼저 와도 본편이 오면 본편이 같은 키를 덮어쓴다 (upsert)
    m2 = maps()
    first = prices(route(env("사이버펑크 2077 얼티밋 에디션", "PS4", 19000), m2))
    after = prices(route(env("사이버펑크 2077 한국어", "PS4", 25000), m2))
    assert first[0]["variant_name"] == "얼티밋 에디션"
    assert after[0]["variant_name"] is None and after[0]["price_krw"] == 25000
    assert prices(route(env("사이버펑크 2077 얼티밋 에디션", "PS4", 15000), m2)) == []


def test_cheapest_edition_within_round_and_new_round_updates():
    m = maps()
    assert prices(route(env("사이버펑크 2077 얼티밋 에디션", "PS5", 45000), m))
    # 같은 회차에 더 비싼 다른 에디션은 싣지 않고, 더 싼 것은 싣는다
    assert not prices(route(env("사이버펑크 2077 디럭스 에디션", "PS5", 50000), m))
    assert prices(route(env("사이버펑크 2077 컴플리트 에디션", "PS5", 41000), m))
    # 다음 회차(6시간 뒤)에는 값이 올라도 새 값으로 싣는다
    nxt = prices(
        route(env("사이버펑크 2077 얼티밋 에디션", "PS5", 47000, at="2026-11-23T21:40:00Z"), m)
    )
    assert nxt[0]["price_krw"] == 47000


def test_collect_round_groups_one_run():
    # KST 00:30 시작(=UTC 15:30) ~ 3시간 동안은 같은 회차
    assert collect_round("2026-11-23T15:31:00Z") == collect_round("2026-11-23T18:20:00Z")
    assert collect_round("2026-11-23T15:31:00Z") != collect_round("2026-11-23T21:31:00Z")


def test_hint_match_uses_searched_game():
    m = Maps()  # 별칭이 없어도
    r = route(env("캡콤 몬스터 헌터 와일즈 한글판", "PS5", 59800, query="몬스터 헌터 와일즈"), m)
    assert prices(r)[0]["game_id"] == CYBERPUNK  # 검색한 게임(igdb_id)으로
    # 검색어가 상품명에 없으면(스핀오프 등) 쓰지 않는다
    r = route(env("케이던스 오브 하이랄", "Switch", 30000, query="Crypt of the NecroDancer"), m)
    assert prices(r) == [] and r["unmatched"]
    # 후속작 숫자는 다른 게임
    assert not hint_match("다키스트 던전 2 PS5", "다키스트 던전")
    assert hint_match("다키스트 던전 PS4 한글판", "다키스트 던전")


def test_platform_from_bundle_and_category():
    assert (
        infer_platform({"product_name": "사이버펑크 2077", "bundle_name": "PS5, 패키지디스크"})
        == "PS5"
    )
    assert (
        infer_platform({"product_name": "x", "category": ["게임", "콘솔게임", "SWITCH2-SW"]})
        == "Switch2"
    )
    assert infer_platform({"product_name": "x"}) is None


def test_schema_matches_contract_and_state_file(tmp_path):
    ex = json.loads(
        (ROOT / "docs/contracts/messages/refined.prices.json").read_text(encoding="utf-8")
    )
    assert ex["schema"]["fields"] == REFINED_PRICE_SCHEMA["fields"]
    lp = LastPrices()
    row = {
        "game_id": 1,
        "store": "danawa",
        "edition": "physical",
        "platform": "PS5",
        "item_condition": "new",
        "price_krw": 1000,
        "variant_name": "얼티밋 에디션",
        "collected_at": "2026-11-23T15:40:00Z",
    }
    assert lp.console_keep(row) and lp.is_new(row)
    p = tmp_path / "s.json"
    lp.save(str(p))
    again = LastPrices.load(str(p))
    assert again.picks and again.last
    assert not again.console_keep({**row, "price_krw": 2000})
    # 예전 형식(last 만)도 읽는다
    p.write_text(json.dumps({"1:steam:digital:PC:new": [1, "KRW", None]}), encoding="utf-8")
    old = LastPrices.load(str(p))
    assert old.last and old.picks == {}
