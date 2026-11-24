"""#93: 본편이 없는 플랫폼은 에디션 가격을 쓴다, 검색어(igdb_id) 힌트, 플랫폼 표기."""

from refiner.router import Maps, route
from refiner.rules.console import ConsoleBest, infer_platform
from refiner.rules.danawa_match import exclude_reason, hint_match

CYBERPUNK = 1877


def env(
    title, platform, price, condition="new", at="2026-11-23T00:30:00Z", query="사이버펑크 2077"
):
    return {
        "source": "danawa",
        "kind": "console_price",
        "collected_at": at,
        "request": {"params": {"query": query, "igdb_id": CYBERPUNK}},
        "payload": {
            "pcode": title[:8],
            "product_name": title,
            "platform_hint": platform,
            "condition": condition,
            "medium": "disc",
            "lowest_price": price,
        },
    }


def prices(r):
    return [m[2]["payload"] for m in r["out"] if m[0] == "prices"]


def test_cyberpunk_ps5_switch2_edition_only_platforms_get_prices():
    maps = Maps({"alias": {"사이버펑크 2077": CYBERPUNK}})
    for title, plat, price, cond in [
        ("사이버펑크 2077 얼티밋 에디션 한국어", "PS5", 42800, "new"),
        ("사이버펑크 2077 얼티밋 에디션 한국어", "PS5", 79900, "used"),
        ("사이버펑크 2077 얼티밋 에디션 한국어", "Switch2", 81800, "new"),
    ]:
        (row,) = prices(route(env(title, plat, price, cond), maps))
        assert (row["game_id"], row["platform"], row["item_condition"], row["price_krw"]) == (
            CYBERPUNK,
            plat,
            cond,
            price,
        )


def test_base_wins_over_edition_on_same_platform_either_order():
    maps = Maps({"alias": {"사이버펑크 2077": CYBERPUNK}})
    # 본편이 먼저 → 에디션은 더 싸도 보내지 않는다
    assert prices(route(env("사이버펑크 2077 한국어", "PS4", 30000), maps))[0]["price_krw"] == 30000
    r = route(env("사이버펑크 2077 GOTY 에디션", "PS4", 20000), maps)
    assert prices(r) == [] and r["unmatched"][0]["reason"] == "에디션 (본편 있음)"
    # 에디션이 먼저 → 나중에 온 본편이 덮어쓴다 (더 비싸도)
    maps2 = Maps({"alias": {"사이버펑크 2077": CYBERPUNK}})
    assert prices(route(env("사이버펑크 2077 얼티밋 에디션", "PS4", 25000), maps2))
    assert (
        prices(route(env("사이버펑크 2077 한국어", "PS4", 35000), maps2))[0]["price_krw"] == 35000
    )


def test_same_kind_keeps_cheapest_and_new_cycle_resets():
    best = ConsoleBest()
    key = (1, "physical", "PS5", "new")
    from datetime import datetime

    t0 = datetime(2026, 11, 23, 0, 30)
    assert best.offer(key, False, 50000, t0)
    assert not best.offer(key, False, 60000, t0)  # 같은 회차, 더 비쌈
    assert best.offer(key, False, 45000, t0)  # 더 쌈
    t1 = datetime(2026, 11, 23, 6, 30)  # 다음 회차
    assert best.offer(key, False, 55000, t1)  # 값이 올라도 새 회차 첫 상품은 보낸다


def test_remaster_and_goods_bundle_still_excluded():
    assert exclude_reason("다크 소울 리마스터 PS4") == "리마스터·굿즈 동봉"
    maps = Maps({"alias": {"사이버펑크 2077": CYBERPUNK}})
    r = route(env("사이버펑크 2077 리마스터", "PS5", 30000), maps)
    assert prices(r) == [] and r["unmatched"][0]["reason"] == "리마스터·굿즈 동봉"


def test_query_hint_when_alias_missing():
    # 별칭에 한글 이름이 없어도 검색어가 상품명에 있으면 수집 때 검색한 게임
    maps = Maps({"alias": {"Forza Horizon 6": 999}})
    e = env(
        "Microsoft Game Studio 포르자 호라이즌 6 한글판",
        "XboxSeries",
        69800,
        query="포르자 호라이즌 6",
    )
    e["request"]["params"]["igdb_id"] = 999
    assert prices(route(e, maps))[0]["game_id"] == 999
    # 검색 결과에 섞인 후속작·다른 게임은 검색어가 없거나 숫자가 달라 쓰지 않는다
    assert not hint_match("하데스 2 한글판", "하데스")
    assert not hint_match("케이던스 오브 하이랄 스위치", "크립트 오브 더 네크로댄서")
    assert hint_match("캡콤 몬스터 헌터 와일즈 한글판 PS5", "몬스터 헌터 와일즈")
    # 검색어가 너무 짧으면 쓰지 않는다
    assert not hint_match("XYZ 게임", "XYZ")


def test_more_platform_spellings():
    for title, plat in [
        ("엑스박스 시리즈 포르자", "XboxSeries"),
        ("엑스박스 원 헤일로", "XboxOne"),
        ("플스5 스파이더맨", "PS5"),
        ("NSW 젤다", "Switch"),
    ]:
        assert infer_platform({"product_name": title}) == plat, title
