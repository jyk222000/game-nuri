import copy

from refiner.rules.price import (
    DEFAULT_RATES,
    dedupe_by_key,
    message_key,
    refine_price,
    store_code,
    to_connect_message,
)

ITAD_ID = "018d937f-590c-728b-ac35-38bcff85f086"


def envelope(deals):
    return {
        "schema_version": 1,
        "source": "itad",
        "kind": "price",
        "collected_at": "2026-11-19T02:30:00Z",
        "payload": {"id": ITAD_ID, "deals": deals},
    }


def deal(shop_id, name, amount, cur="KRW", reg=None, cut=0):
    return {
        "shop": {"id": shop_id, "name": name},
        "price": {"amount": amount, "currency": cur},
        "regular": {"amount": reg if reg is not None else amount, "currency": cur},
        "cut": cut,
        "url": f"https://example.com/{shop_id}",
    }


def resolver(m):
    return lambda k: m.get(k)


def test_krw_kept_and_fields_filled():
    rows, un = refine_price(
        envelope([deal(61, "Steam", 47900, reg=64800, cut=26)]), resolver({ITAD_ID: 119133})
    )
    assert un == []
    assert rows == [
        {
            "game_id": 119133,
            "store": "steam",
            "edition": "digital",
            "platform": "PC",
            "item_condition": "new",
            "price_krw": 47900,
            "regular_krw": 64800,
            "discount_pct": 26,
            "price_original": 47900,
            "currency_original": "KRW",
            "url": "https://example.com/61",
            "collected_at": "2026-11-19T02:30:00Z",
        }
    ]


def test_foreign_currency_converted_and_original_kept():
    rows, _ = refine_price(
        envelope([deal(16, "Epic", 50.0, "USD", reg=60.0)]), resolver({ITAD_ID: 1})
    )
    r = rows[0]
    assert r["price_krw"] == int(50.0 * DEFAULT_RATES["USD"])
    assert r["regular_krw"] == int(60.0 * DEFAULT_RATES["USD"])
    assert (r["price_original"], r["currency_original"]) == (50.0, "USD")


def test_unmatched_game_goes_to_unmatched_not_dropped():
    rows, un = refine_price(envelope([deal(61, "Steam", 1000)]), resolver({}))
    assert rows == []
    assert un[0]["key"] == ITAD_ID and "매칭 실패" in un[0]["reason"]


def test_unknown_currency_is_unmatched_not_zero():
    rows, un = refine_price(envelope([deal(61, "Steam", 10, "JPY")]), resolver({ITAD_ID: 1}))
    assert rows == [] and len(un) == 1


def test_missing_regular_is_none():
    d = deal(61, "Steam", 1000)
    d["regular"] = None
    rows, _ = refine_price(envelope([d]), resolver({ITAD_ID: 1}))
    assert rows[0]["regular_krw"] is None


def test_same_key_keeps_lower_price():
    rows, _ = refine_price(
        envelope([deal(61, "Steam", 3000), deal(61, "Steam", 2000)]), resolver({ITAD_ID: 1})
    )
    assert [r["price_krw"] for r in rows] == [2000]


def test_idempotent_same_input_same_output():
    env = envelope([deal(61, "Steam", 3000), deal(20, "GameBillet", 5000)])
    a = refine_price(copy.deepcopy(env), resolver({ITAD_ID: 1}))
    b = refine_price(copy.deepcopy(env), resolver({ITAD_ID: 1}))
    assert a == b


def test_store_code_and_key_and_message_shape():
    assert store_code({"id": 61, "name": "Steam"}) == "steam"
    assert store_code({"id": 20, "name": "Game Billet!"}) == "gamebillet"
    rows, _ = refine_price(envelope([deal(61, "Steam", 1000)]), resolver({ITAD_ID: 7}))
    assert message_key(rows[0]) == "7:steam:digital:PC:new"
    assert rows[0]["platform"] == "PC" and rows[0]["item_condition"] == "new"
    msg = to_connect_message(rows[0])
    assert set(msg) == {"schema", "payload"}
    assert {f["field"] for f in msg["schema"]["fields"]} == set(rows[0])


def test_dedupe_by_key_order_kept():
    base = {"edition": "digital", "platform": "PC", "item_condition": "new", "price_krw": 5}
    a = {"game_id": 1, "store": "a", **base}
    b = {"game_id": 1, "store": "b", **base}
    assert dedupe_by_key([a, b]) == [a, b]


def test_dedupe_keeps_platforms_and_conditions_apart():
    base = {"game_id": 1, "store": "danawa", "edition": "physical", "price_krw": 5}
    rows = [
        {**base, "platform": "PS5", "item_condition": "new"},
        {**base, "platform": "PS4", "item_condition": "new"},
        {**base, "platform": "PS5", "item_condition": "used"},
    ]
    assert dedupe_by_key(rows) == rows
