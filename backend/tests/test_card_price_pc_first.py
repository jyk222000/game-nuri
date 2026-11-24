"""카드 현재가는 PC 새 상품 최저가가 기준이다(콘솔 전용이면 전체 플랫폼). #94."""

from datetime import timedelta

from app.db.models import PriceCurrent, PriceHistory

from tests.conftest import NOW, seed


def _cur(game_id, platform, price, store="steam", regular=None, pct=None, cond="new"):
    return PriceCurrent(
        game_id=game_id,
        store=store,
        edition="digital",
        platform=platform,
        item_condition=cond,
        price_krw=price,
        regular_krw=regular,
        discount_pct=pct,
        collected_at=NOW,
    )


def _hist(hid, game_id, platform, price, days_ago, store="steam", pct=0, cond="new"):
    return PriceHistory(
        id=hid,
        game_id=game_id,
        store=store,
        edition="digital",
        platform=platform,
        item_condition=cond,
        price_krw=price,
        regular_krw=65900,
        discount_pct=pct,
        collected_at=NOW - timedelta(days=days_ago),
    )


def _card(client, game_id):
    return client.get(f"/api/games/{game_id}").json()


def test_card_uses_pc_price_even_when_console_is_cheaper(env) -> None:
    """콘솔(다나와)은 정가·할인율이 없다. 더 싸도 카드는 PC의 가격·정가·할인율을 보여 준다."""
    client, engine, _ = env
    with seed(engine) as s:
        s.add_all(
            [
                _cur(7, "PC", 19770, store="msstore", regular=65900, pct=70),
                _cur(7, "PS4", 11810, store="danawa"),  # 콘솔: regular·discount 없음
            ]
        )
    card = _card(client, 7)
    assert (card["price_krw"], card["regular_krw"], card["discount_pct"]) == (19770, 65900, 70)


def test_console_only_game_keeps_its_price(env) -> None:
    client, engine, _ = env
    with seed(engine) as s:
        s.add_all(
            [_cur(5, "PS5", 42800, store="danawa"), _cur(5, "Switch2", 81800, store="danawa")]
        )
    assert _card(client, 5)["price_krw"] == 42800  # 콘솔 전용: 전체 플랫폼 최저가


def test_pc_used_is_ignored_and_console_new_does_not_win(env) -> None:
    client, engine, _ = env
    with seed(engine) as s:
        s.add_all(
            [
                _cur(7, "PC", 50000, regular=64800, pct=23),
                _cur(7, "PC", 1000, store="gamestop", cond="used"),  # 중고는 기존처럼 제외
                _cur(7, "XboxOne", 9000, store="danawa"),
            ]
        )
    assert _card(client, 7)["price_krw"] == 50000


def test_price_sort_uses_card_price(env) -> None:
    """가격순 정렬도 카드와 같은 기준. 7번은 콘솔이 더 싸지만 PC 50,000원으로 정렬된다."""
    client, engine, _ = env
    with seed(engine) as s:
        s.add_all(
            [
                _cur(7, "PC", 50000, regular=64800, pct=23),
                _cur(7, "PS4", 11810, store="danawa"),
                _cur(5, "PS5", 42800, store="danawa"),  # 콘솔 전용
            ]
        )
    ids = [i["game_id"] for i in client.get("/api/games?sort=price").json()["items"]]
    assert ids.index(5) < ids.index(7)  # 42,800 < 50,000


def test_deals_keep_game_whose_pc_price_is_discounted(env) -> None:
    """콘솔 값이 카드 가격이면 할인 표시가 사라져 할인 목록에서 빠지던 게임이 다시 나온다."""
    client, engine, _ = env
    with seed(engine) as s:
        s.add_all(
            [
                _cur(7, "PC", 19770, store="msstore", regular=65900, pct=70),
                _cur(7, "PS4", 11810, store="danawa"),
            ]
        )
    items = client.get("/api/games/deals").json()["items"]
    assert [(i["game_id"], i["price_krw"], i["discount_pct"]) for i in items] == [(7, 19770, 70)]


def test_card_price_matches_timing_current(env) -> None:
    """카드 현재가와 /timing의 current_krw가 같다(둘 다 PC 기준)."""
    client, engine, _ = env
    with seed(engine) as s:
        s.add_all(
            [
                _cur(7, "PC", 19770, store="msstore", regular=65900, pct=70),
                _cur(7, "PS4", 11810, store="danawa"),
                _hist(1, 7, "PC", 65900, 30, store="msstore"),
                _hist(2, 7, "PC", 19770, 10, store="msstore", pct=70),
                _hist(3, 7, "PC", 65900, 2, store="steam"),
                _hist(4, 7, "PS4", 11810, 1, store="danawa"),
            ]
        )
    timing = client.get("/api/games/7/timing").json()
    assert _card(client, 7)["price_krw"] == timing["current_krw"] == 19770


def test_detail_lowest_uses_pc_when_available(env) -> None:
    """역대 최저가(lowest_krw)도 카드와 같은 기준: PC가 있으면 PC 안에서."""
    client, engine, _ = env
    with seed(engine) as s:
        s.add_all(
            [
                _cur(7, "PC", 40000, regular=64800, pct=38),
                _hist(1, 7, "PC", 30000, 50),
                _hist(2, 7, "PS4", 10000, 5, store="danawa"),  # 콘솔 이력은 섞지 않는다
            ]
        )
    assert _card(client, 7)["lowest_krw"] == 30000


def test_detail_lowest_falls_back_for_console_only(env) -> None:
    client, engine, _ = env
    with seed(engine) as s:
        s.add_all(
            [
                _cur(5, "PS5", 42800, store="danawa"),
                _hist(1, 5, "PS5", 39800, 3, store="danawa"),
            ]
        )
    assert _card(client, 5)["lowest_krw"] == 39800
