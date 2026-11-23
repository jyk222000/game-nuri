"""#14 환율: USD·EUR·GBP만, 통화별 최신 기준일."""

from datetime import date
from decimal import Decimal

from app.db.models import ExchangeRate

from tests.conftest import seed


def test_rates_latest_per_currency(env) -> None:
    client, engine, _ = env
    with seed(engine) as s:
        s.add_all(
            [
                ExchangeRate(
                    rate_date=date(2026, 11, 20), currency="USD", krw_per_unit=Decimal("1380.0")
                ),
                ExchangeRate(
                    rate_date=date(2026, 11, 21), currency="USD", krw_per_unit=Decimal("1385.2")
                ),
                ExchangeRate(
                    rate_date=date(2026, 11, 21), currency="EUR", krw_per_unit=Decimal("1502.8")
                ),
                ExchangeRate(
                    rate_date=date(2026, 11, 20), currency="GBP", krw_per_unit=Decimal("1760.4")
                ),
                ExchangeRate(
                    rate_date=date(2026, 11, 21), currency="JPY", krw_per_unit=Decimal("9.1")
                ),
            ]
        )
    assert client.get("/api/exchange-rates").json() == {
        "base": "KRW",
        "rates": {"EUR": 1502.8, "GBP": 1760.4, "USD": 1385.2},  # JPY는 내보내지 않는다
        "updated_at": "2026-11-21T00:00:00Z",
    }


def test_rates_empty(env) -> None:
    client, *_ = env
    assert client.get("/api/exchange-rates").json() == {
        "base": "KRW",
        "rates": {},
        "updated_at": None,
    }
