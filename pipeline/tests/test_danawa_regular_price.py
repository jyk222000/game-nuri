"""#132 다나와 정가: 신품은 출시가로 regular_krw·discount_pct 를 채운다."""

from refiner.rules.console import refine_console_price, regular_and_discount, release_price

CYBERPUNK = 1877


def env(price, condition="new", release="/출시가: 72,000원"):
    return {
        "source": "danawa",
        "kind": "console_price",
        "collected_at": "2026-11-25T15:40:00Z",
        "payload": {
            "pcode": "1",
            "product_name": "CD프로젝트레드 사이버펑크 2077 한글판",
            "platform_hint": "PS5",
            "condition": condition,
            "lowest_price": price,
            "release_price_text": release,
        },
    }


def refine(e):
    rows, _ = refine_console_price(e, lambda _t: CYBERPUNK)
    return rows[0]


def test_release_price_parse():
    assert release_price("/출시가: 72,000원") == 72000
    assert release_price("출시가 232,200원") == 232200
    assert release_price(None) is None
    assert release_price("") is None
    assert release_price("/출시가: 0원") is None


def test_new_with_release_price_fills_discount():
    row = refine(env(43380))
    assert row["regular_krw"] == 72000
    assert row["discount_pct"] == 40  # 1 - 43380/72000 = 39.75%


def test_price_above_release_is_zero_discount():
    assert regular_and_discount(129800, "new", "/출시가: 28,800원") == (28800, 0)


def test_used_stays_empty():
    row = refine(env(28110, condition="used", release="/출시가: 64,800원"))
    assert row["regular_krw"] is None and row["discount_pct"] is None


def test_no_release_price_stays_empty():
    row = refine(env(43380, release=None))
    assert row["regular_krw"] is None and row["discount_pct"] is None
