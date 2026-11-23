"""raw.price(kind=price_history, ITAD games/history/v2) → refined.price_history.

봉투 payload 형식 (수집기):
  {"id": "<itad_id>", "history": [ITAD history/v2 응답 항목 ...]}
  (payload 가 항목 목록 그대로이면 itad_id 는 request.params.id 에서 찾는다)
항목: {"timestamp": "2026-11-07T14:21:21+01:00", "shop": {...},
       "deal": {"price": {"amount", "currency"}, "regular": {...}, "cut": 12}}

규칙
  - 항목 하나 = price_history 한 행 (PC, new, digital). 필드는 refined.prices 와 같다.
  - collected_at = 항목 timestamp 를 UTC "...Z" 로 (R04). 수집 시각이 아니라 가격이 바뀐 시각이다.
  - 원화 = 그 날짜가 속한 달의 환율 (rules/rates.py).
    price_original·currency_original 은 원본 그대로.
  - 같은 이력을 다시 받아도 같은 행이 나온다 (멱등). price_history 는 insert 라 줄이 겹칠 수 있고,
    Backend 가 키 6개로 합친다 (backend/app/services/history.py).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from refiner.rules.price import store_code
from refiner.rules.rates import RateBook


def to_utc_z(ts: str | None) -> str | None:
    """ISO 시각(오프셋 포함) → UTC "YYYY-MM-DDTHH:MM:SSZ". 읽을 수 없으면 None."""
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _krw(amount: Any, currency: str | None, day: str, book: RateBook) -> int | None:
    if amount is None:
        return None
    r = book.rate(currency, day)
    return None if r is None else int(round(float(amount) * r))


def refine_price_history(
    envelope: dict[str, Any],
    resolve_game_id: Callable[[str], int | None],
    book: RateBook,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """→ (price_history 행 목록, unmatched 목록)."""
    payload = envelope.get("payload")
    params = (envelope.get("request") or {}).get("params") or {}
    if isinstance(payload, dict):
        itad_id = payload.get("id") or params.get("id")
        items = payload.get("history") or []
    else:
        itad_id = params.get("id")
        items = payload or []
    at = envelope.get("collected_at")
    game_id = resolve_game_id(itad_id) if itad_id else None
    if game_id is None:
        return [], [
            {
                "reason": "itad_id → IGDB ID 매칭 실패 (가격 이력)",
                "source": "itad",
                "key": itad_id,
                "collected_at": at,
            }
        ]

    rows: list[dict[str, Any]] = []
    unmatched: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for it in items:
        deal = it.get("deal") or {}
        price = deal.get("price") or {}
        regular = deal.get("regular") or {}
        when = to_utc_z(it.get("timestamp"))
        cur = price.get("currency")
        price_krw = _krw(price.get("amount"), cur, when or "", book) if when else None
        if when is None or price_krw is None:
            unmatched.append(
                {
                    "reason": "이력 항목에 시각·가격·통화가 없음",
                    "source": "itad",
                    "key": itad_id,
                    "collected_at": at,
                    "detail": {"timestamp": it.get("timestamp"), "price": price},
                }
            )
            continue
        store = store_code(it.get("shop") or {})
        if (store, when) in seen:  # 같은 응답 안의 중복
            continue
        seen.add((store, when))
        rows.append(
            {
                "game_id": int(game_id),
                "store": store,
                "edition": "digital",
                "platform": "PC",
                "item_condition": "new",
                "price_krw": price_krw,
                "regular_krw": _krw(regular.get("amount"), regular.get("currency"), when, book),
                "discount_pct": deal.get("cut"),
                "price_original": price.get("amount"),
                "currency_original": cur,
                "url": None,
                "collected_at": when,
            }
        )
    return rows, unmatched


def message_key(row: dict[str, Any]) -> str:
    """키 = game_id:store:edition:platform:item_condition:collected_at (Backend 합치기 기준)."""
    return ":".join(
        str(row[k])
        for k in ("game_id", "store", "edition", "platform", "item_condition", "collected_at")
    )
