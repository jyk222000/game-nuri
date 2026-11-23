from refiner.router import OUT_TOPICS, Maps, route
from refiner.rules.price_history import to_utc_z
from refiner.rules.rates import RateBook

HISTORY = [
    {
        "timestamp": "2026-11-07T14:21:21+01:00",
        "shop": {"id": 20, "name": "GameBillet"},
        "deal": {
            "price": {"amount": 52.69, "currency": "USD"},
            "regular": {"amount": 59.99, "currency": "USD"},
            "cut": 12,
        },
    },
    {
        "timestamp": "2022-10-02T05:10:46+02:00",
        "shop": {"id": 61, "name": "Steam"},
        "deal": {
            "price": {"amount": 29.99, "currency": "USD"},
            "regular": {"amount": 59.99, "currency": "USD"},
            "cut": 50,
        },
    },
    {
        "timestamp": "2026-08-18T17:26:49+02:00",
        "shop": {"id": 61, "name": "Steam"},
        "deal": {"price": {"amount": 64800, "currency": "KRW"}, "cut": 0},
    },
    {"timestamp": None, "shop": {"id": 61}, "deal": {"price": {"amount": 1, "currency": "USD"}}},
]


def env(payload, **kw):
    return {
        "source": "itad",
        "kind": "price_history",
        "collected_at": "2026-11-23T04:00:00Z",
        "payload": payload,
        **kw,
    }


def test_rates_monthly_file_and_nearest_month():
    book = RateBook.load()
    assert book.rate("USD", "2022-10-02") == 1426.065
    assert book.rate("USD", "2026-11-23") == book.rate("USD", "2026-10-15")  # 표 밖 → 마지막 달
    assert book.rate("USD", "2005-01-01") == book.rate("USD", "2012-01-31")  # 표 앞 → 첫 달
    assert book.rate("KRW", "2020-01-01") == 1.0
    assert book.rate("EUR", "2020-01-01") == 1500.0  # 표에 없는 통화 → 임시 고정값
    assert book.rate_row("USD", "2022-10-02") == {
        "rate_date": "2022-10-01",
        "currency": "USD",
        "krw_per_unit": 1426.065,
    }


def test_to_utc_z():
    assert to_utc_z("2026-11-07T14:21:21+01:00") == "2026-11-07T13:21:21Z"
    assert to_utc_z("2026-11-07T14:21:21Z") == "2026-11-07T14:21:21Z"
    assert to_utc_z("nope") is None


def test_history_rows_monthly_krw_and_rates():
    maps = Maps({"itad": {"itad-1": 119133}})
    maps.rates = RateBook.load()
    res = route(env({"id": "itad-1", "history": HISTORY}), maps)
    hist = [(k, m["payload"]) for n, k, m in res["out"] if n == "price_history"]
    assert len(hist) == 3 and len(res["unmatched"]) == 1
    k, old = hist[1]
    assert k == "119133:steam:digital:PC:new:2022-10-02T03:10:46Z"
    assert old["price_krw"] == round(29.99 * 1426.065) and old["regular_krw"] == round(
        59.99 * 1426.065
    )
    assert old["discount_pct"] == 50 and old["currency_original"] == "USD"
    assert hist[2][1]["price_krw"] == 64800  # 원화는 그대로
    rates = sorted(m["payload"]["rate_date"] for n, _, m in res["out"] if n == "exchange_rates")
    assert rates == ["2022-10-01", "2026-10-01"]  # 2026-11 은 표에 없어 10월 값
    again = route(env({"id": "itad-1", "history": HISTORY}), maps)
    assert [m["payload"] for n, _, m in again["out"] if n == "price_history"] == [
        p for _, p in hist
    ]
    assert not [n for n, _, _ in again["out"] if n == "exchange_rates"]  # 환율은 한 번만


def test_history_list_payload_and_unmatched():
    maps = Maps({"itad": {"itad-1": 1}})
    res = route(env(HISTORY[:1], request={"params": {"id": "itad-1"}}), maps)
    assert [n for n, _, _ in res["out"]].count("price_history") == 1
    res = route(env({"id": "모름", "history": HISTORY}), maps)
    assert res["out"] == [] and "매칭 실패" in res["unmatched"][0]["reason"]


def test_out_topic():
    assert OUT_TOPICS["price_history"] == "refined.price_history"
