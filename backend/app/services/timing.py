"""구매 타이밍(#15)과 할인 예측(#16). price_history는 읽기만 한다.

판정 규칙은 docs/contracts/timing_rules.md(analysis 담당, A1)가 확정되기 전의 **임시 값**이다
(프런트 목업 `router.js`의 규칙과 같다). 규칙을 바꿀 때는 아래 상수만 고친다.

기준 이력: PC·새 상품(item_condition='new') 이력. 하루에 여러 건이면 그날 최저가 한 줄만 쓴다.
PC 이력이 없거나(콘솔 전용 등) 이력 일수가 MIN_HISTORY_DAYS 미만이면 insufficient_data다.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import PriceHistory
from app.schemas.timing import PredictionOut, TimingOut
from app.services import games

# ---------- 임시 규칙 (analysis 확정 후 교체) ----------
TIMING_PLATFORM = "PC"
SALE_MIN_PCT = 10  # 이 할인율 이상인 날이 이어진 구간 = 할인(세일) 1회
BUY_NOW_MIN_PCT = 30  # buy_now: 이 할인율 이상이고 역대 최저가 근처
NEAR_LOW_RATIO = 1.05  # 역대 최저가의 105% 이하면 '근처'
NEUTRAL_MIN_PCT = 10  # neutral: 이 할인율 이상 (그보다 낮으면 wait)
MIN_HISTORY_DAYS = 3  # 이력이 이 일수 미만이면 insufficient_data
WINDOW_DAYS = 730  # 할인 횟수·주기 계산 기간 (최근 2년)
FALLBACK_NEXT_DAYS = 14  # 예상일이 이미 지났으면 오늘로부터 이만큼 뒤
CONFIDENCE_HIGH_MIN_SALES = 8
CONFIDENCE_MEDIUM_MIN_SALES = 4


@dataclass(frozen=True)
class Day:
    day: date
    price_krw: int
    discount_pct: int  # 없으면 0


@dataclass(frozen=True)
class Sale:
    start: date
    max_pct: int


def _now(now: datetime | None) -> datetime:
    return now or datetime.now(UTC).replace(tzinfo=None)  # DB는 UTC naive


def daily_series(db: Session, game_id: int) -> tuple[list[Day], bool]:
    """(날짜 오름차순 일별 최저가, PC·새 상품 외 다른 이력이 있는지)."""
    rows = db.scalars(select(PriceHistory).where(PriceHistory.game_id == game_id)).all()
    best: dict[date, PriceHistory] = {}
    has_other = False
    for r in rows:
        if r.platform != TIMING_PLATFORM or r.item_condition != "new":
            has_other = True
            continue
        d = r.collected_at.date()
        cur = best.get(d)
        if cur is None or (r.price_krw, r.store, r.edition) < (
            cur.price_krw,
            cur.store,
            cur.edition,
        ):
            best[d] = r
    days = [Day(d, r.price_krw, r.discount_pct or 0) for d, r in sorted(best.items())]
    return days, has_other


def sale_events(days: list[Day]) -> list[Sale]:
    """할인율이 SALE_MIN_PCT 이상인 날이 이어진 구간마다 한 건."""
    events: list[Sale] = []
    start: date | None = None
    top = 0
    for d in days:
        if d.discount_pct >= SALE_MIN_PCT:
            if start is None:
                start, top = d.day, d.discount_pct
            else:
                top = max(top, d.discount_pct)
        elif start is not None:
            events.append(Sale(start, top))
            start = None
    if start is not None:
        events.append(Sale(start, top))
    return events


def _recent(days: list[Day], now: datetime) -> list[Day]:
    since = (now - timedelta(days=WINDOW_DAYS)).date()
    return [d for d in days if d.day >= since]


def _confidence(sales: int) -> str:
    if sales >= CONFIDENCE_HIGH_MIN_SALES:
        return "high"
    if sales >= CONFIDENCE_MEDIUM_MIN_SALES:
        return "medium"
    return "low"


def _insufficient_prediction(game_id: int, basis: str) -> PredictionOut:
    return PredictionOut(
        game_id=game_id,
        avg_sale_interval_days=None,
        next_sale_expected=None,
        expected_discount_pct=None,
        confidence="insufficient_data",
        basis=basis,
    )


def _predict(game_id: int, days: list[Day], now: datetime) -> PredictionOut:
    if len(days) < MIN_HISTORY_DAYS:
        return _insufficient_prediction(game_id, "가격 이력이 부족해요")
    events = sale_events(_recent(days, now))
    if len(events) < 2:  # 간격을 구하려면 최소 2회가 필요하다
        return _insufficient_prediction(
            game_id, "최근 2년 할인이 2회 미만이라 주기를 구할 수 없어요"
        )
    gaps = [(b.start - a.start).days for a, b in zip(events, events[1:], strict=False)]
    avg = round(sum(gaps) / len(gaps))
    nxt = events[-1].start + timedelta(days=avg)
    if nxt < now.date():  # 예상일이 이미 지났으면 곧 올 것으로 본다
        nxt = (now + timedelta(days=FALLBACK_NEXT_DAYS)).date()
    return PredictionOut(
        game_id=game_id,
        avg_sale_interval_days=avg,
        next_sale_expected=nxt.isoformat(),
        expected_discount_pct=round(sum(e.max_pct for e in events) / len(events)),
        confidence=_confidence(len(events)),
        basis=f"최근 2년 할인 {len(events)}회 기준",
    )


def get_prediction(db: Session, game_id: int, now: datetime | None = None) -> PredictionOut:
    games.ensure_exists(db, game_id)
    days, _ = daily_series(db, game_id)
    return _predict(game_id, days, _now(now))


def get_timing(db: Session, game_id: int, now: datetime | None = None) -> TimingOut:
    games.ensure_exists(db, game_id)
    now = _now(now)
    days, has_other = daily_series(db, game_id)
    if len(days) < MIN_HISTORY_DAYS:
        reason = (
            "콘솔은 가격 이력이 짧아 아직 판단하기 어려워요."
            if not days and has_other
            else "가격 이력이 부족해 아직 판단하기 어려워요."
        )
        return TimingOut(
            game_id=game_id,
            verdict="insufficient_data",
            reason=reason,
            current_krw=None,
            lowest_krw=None,
            lowest_date=None,
            vs_lowest_pct=None,
            sale_count_2y=None,
        )

    current = days[-1]
    low = min(days, key=lambda d: (d.price_krw, d.day))  # 역대(전체 이력) 최저가, 동점은 이른 날짜
    near_low = current.price_krw <= low.price_krw * NEAR_LOW_RATIO

    if current.discount_pct >= BUY_NOW_MIN_PCT and near_low:
        verdict, reason = "buy_now", "역대 최저가에 가까운 가격이에요. 지금 사도 손해가 적어요."
    elif current.discount_pct >= NEUTRAL_MIN_PCT:
        verdict = "neutral"
        reason = (
            f"할인 중이지만 역대 최저가({low.price_krw:,}원)보다는 높아요. "
            "급하지 않다면 더 기다려도 좋아요."
        )
    else:
        verdict, reason = "wait", "정가에 가까워요."
        predicted = _predict(game_id, days, now)
        if predicted.next_sale_expected is not None:
            reason += f" 다음 할인은 {predicted.next_sale_expected} 전후로 예상돼요."

    return TimingOut(
        game_id=game_id,
        verdict=verdict,
        reason=reason,
        current_krw=current.price_krw,
        lowest_krw=low.price_krw,
        lowest_date=low.day.isoformat(),
        vs_lowest_pct=round((current.price_krw / low.price_krw - 1) * 100),
        sale_count_2y=len(sale_events(_recent(days, now))),
    )
