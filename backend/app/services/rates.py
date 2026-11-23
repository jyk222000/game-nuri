"""원화 환산 기준 환율(#14). exchange_rates는 읽기만 한다. USD·EUR·GBP만 내보낸다."""

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import ExchangeRate
from app.schemas.price import ExchangeRatesOut

CURRENCIES = ("USD", "EUR", "GBP")


def get_rates(db: Session) -> ExchangeRatesOut:
    """통화별로 가장 최근 기준일의 값을 쓰고, updated_at은 그중 가장 늦은 기준일이다."""
    latest = (
        select(ExchangeRate.currency, func.max(ExchangeRate.rate_date).label("d"))
        .where(ExchangeRate.currency.in_(CURRENCIES))
        .group_by(ExchangeRate.currency)
        .subquery()
    )
    rows = db.execute(
        select(ExchangeRate.currency, ExchangeRate.rate_date, ExchangeRate.krw_per_unit).join(
            latest,
            (ExchangeRate.currency == latest.c.currency) & (ExchangeRate.rate_date == latest.c.d),
        )
    ).all()
    rates = {cur: float(value) for cur, _, value in sorted(rows, key=lambda r: r[0])}
    updated = max((d for _, d, _ in rows), default=None)
    return ExchangeRatesOut(
        rates=rates,
        updated_at=datetime(updated.year, updated.month, updated.day) if updated else None,
    )
