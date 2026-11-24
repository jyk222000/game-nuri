"""#12 역대 최저가: platform·item_condition별 한 건."""

from datetime import datetime

from app.db.models import PriceHistory

from tests.conftest import seed


def _h(id_, ts, price, store="steam", edition="digital", platform="PC", cond="new", pct=None):
    return PriceHistory(
        id=id_,
        game_id=119133,
        store=store,
        edition=edition,
        platform=platform,
        item_condition=cond,
        price_krw=price,
        regular_krw=64800 if cond == "new" else None,
        discount_pct=pct,
        collected_at=ts,
    )


def test_lowest_per_platform_and_condition(env) -> None:
    client, engine, _ = env
    with seed(engine) as s:
        s.add_all(
            [
                _h(1, datetime(2025, 12, 5, 3), 38900, pct=40),
                _h(2, datetime(2026, 11, 19, 2), 47900, pct=26),
                _h(3, datetime(2026, 10, 2, 1), 31000, "danawa", "physical", "PS5", "used"),
                _h(4, datetime(2026, 11, 1, 1), 36000, "danawa", "physical", "PS5", "used"),
                _h(5, datetime(2026, 11, 2, 1), 55000, "danawa", "physical", "PS5", "new"),
            ]
        )
    body = client.get("/api/games/119133/lowest").json()
    assert body["game_id"] == 119133
    assert body["items"] == [
        {
            "platform": "PC",
            "item_condition": "new",
            "store": "steam",
            "edition": "digital",
            "price_krw": 38900,
            "regular_krw": 64800,
            "discount_pct": 40,
            "variant_name": None,
            "date": "2025-12-05",
        },
        {
            "platform": "PS5",
            "item_condition": "new",
            "store": "danawa",
            "edition": "physical",
            "price_krw": 55000,
            "regular_krw": 64800,
            "discount_pct": None,
            "variant_name": None,
            "date": "2026-11-02",
        },
        {
            "platform": "PS5",
            "item_condition": "used",
            "store": "danawa",
            "edition": "physical",
            "price_krw": 31000,
            "regular_krw": None,
            "discount_pct": None,
            "variant_name": None,
            "date": "2026-10-02",
        },
    ]


def test_lowest_tie_picks_earliest_then_store(env) -> None:
    client, engine, _ = env
    with seed(engine) as s:
        s.add_all(
            [
                _h(1, datetime(2026, 5, 1), 30000, store="steam"),
                _h(2, datetime(2026, 3, 1), 30000, store="gog"),
                _h(3, datetime(2026, 3, 1), 30000, store="epic"),
                _h(4, datetime(2026, 3, 1), 30000, store="epic"),  # 중복 행이 있어도 한 건
            ]
        )
    items = client.get("/api/games/119133/lowest").json()["items"]
    assert len(items) == 1
    assert (items[0]["store"], items[0]["date"]) == ("epic", "2026-03-01")


def test_lowest_empty_and_404(env) -> None:
    client, *_ = env
    assert client.get("/api/games/5/lowest").json() == {"game_id": 5, "items": []}
    r = client.get("/api/games/999/lowest")
    assert r.status_code == 404 and r.json()["error"]["code"] == "NOT_FOUND"
