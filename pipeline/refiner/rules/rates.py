"""날짜별 환율 (월평균). Kafka 없이 시험할 수 있는 순수 함수.

rates_monthly.csv (month, currency, krw_per_unit) 를 읽어, 날짜가 속한 달의 환율을 돌려준다.
  - 표에 없는 달: 그 통화의 가장 가까운 달 값 (가장 최근 달 이후면 마지막 값)
  - 표에 없는 통화: DEFAULT_RATES (임시 고정값)
  - KRW 는 항상 1
환율을 쓰면 refined.exchange_rates 로 (rate_date = 그 달 1일, currency, krw_per_unit) 를 보낸다.
"""

from __future__ import annotations

import bisect
import csv
from pathlib import Path

from refiner.rules.price import DEFAULT_RATES

DEFAULT_PATH = Path(__file__).resolve().parents[1] / "rates_monthly.csv"


class RateBook:
    def __init__(self, monthly: dict[str, dict[str, float]] | None = None):
        # {통화: {"YYYY-MM": 원화}}
        self.monthly = monthly or {}
        self._months = {cur: sorted(m) for cur, m in self.monthly.items()}

    @classmethod
    def load(cls, path: str | Path | None = None) -> RateBook:
        p = Path(path) if path else DEFAULT_PATH
        if not p.exists():
            return cls()
        monthly: dict[str, dict[str, float]] = {}
        with open(p, encoding="utf-8") as f:
            rows = (line for line in f if line.strip() and not line.startswith("#"))
            for r in csv.DictReader(rows):
                monthly.setdefault(r["currency"].strip(), {})[r["month"].strip()] = float(
                    r["krw_per_unit"]
                )
        return cls(monthly)

    def month_for(self, currency: str, day: str) -> str | None:
        """그 통화에서 실제로 쓸 달 (표에 없으면 가장 가까운 달). 표에 통화가 없으면 None."""
        months = self._months.get(currency)
        if not months:
            return None
        want = day[:7]
        i = bisect.bisect_left(months, want)
        if i < len(months) and months[i] == want:
            return want
        if i == 0:
            return months[0]
        if i == len(months):
            return months[-1]
        before, after = months[i - 1], months[i]
        return before if _gap(before, want) <= _gap(want, after) else after

    def rate(self, currency: str | None, day: str) -> float | None:
        """날짜(YYYY-MM-DD...)의 1단위당 원화. 모르는 통화면 None."""
        if currency == "KRW":
            return 1.0
        if currency is None:
            return None
        m = self.month_for(currency, day)
        if m is not None:
            return self.monthly[currency][m]
        return DEFAULT_RATES.get(currency)

    def rates_for(self, day: str) -> dict[str, float]:
        """그날 쓸 환율 전체 (refine_price 의 rates 인자로)."""
        out = dict(DEFAULT_RATES)
        for cur in self.monthly:
            r = self.rate(cur, day)
            if r is not None:
                out[cur] = r
        return out

    def rate_row(self, currency: str, day: str) -> dict[str, object] | None:
        """exchange_rates 한 행. 월 환율이면 그 달 1일, 고정값이면 그날."""
        r = self.rate(currency, day)
        if r is None or currency == "KRW":
            return None
        m = self.month_for(currency, day)
        rate_date = f"{m}-01" if m else day[:10]
        return {"rate_date": rate_date, "currency": currency, "krw_per_unit": r}


def _gap(a: str, b: str) -> int:
    ya, ma = map(int, a.split("-"))
    yb, mb = map(int, b.split("-"))
    return (yb * 12 + mb) - (ya * 12 + ma)
