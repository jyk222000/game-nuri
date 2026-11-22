"""raw.price(ITAD) → refined.prices 변환. Kafka 없이 테스트할 수 있는 순수 함수.

규칙 (pipeline/CLAUDE.md, docs/contracts/messages/refined.prices.json 기준)
  - 기준 게임 ID는 IGDB ID. ITAD id(uuid)를 resolver로 IGDB ID로 바꾼다. 못 바꾸면 unmatched.
  - KRW면 그대로, 아니면 환율 적용. price_original, currency_original은 항상 채운다.
  - 빈 값은 NULL(None). 0으로 채우지 않는다.
  - edition은 ITAD가 디지털 스토어만 다루므로 "digital", platform은 "PC", item_condition은 "new".
  - 같은 메시지를 두 번 처리해도 결과가 같다 (입력만으로 결정, 시각·난수 사용 안 함).
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from typing import Any

# 환율 (KRW per 1 unit). 팀 결정 전 임시값 — 확정되면 exchange_rates 테이블/설정으로 교체.
DEFAULT_RATES: dict[str, float] = {"KRW": 1.0, "USD": 1400.0, "EUR": 1500.0, "GBP": 1800.0}

# ITAD shop id → 내부 store 코드. 목록에 없으면 이름을 slug로 만든다.
KNOWN_SHOPS: dict[int, str] = {61: "steam"}

REFINED_PRICE_SCHEMA: dict[str, Any] = {
    "type": "struct",
    "name": "refined_price",
    "fields": [
        {"field": "game_id", "type": "int64", "optional": False},
        {"field": "store", "type": "string", "optional": False},
        {"field": "edition", "type": "string", "optional": False},
        {"field": "platform", "type": "string", "optional": False},
        {"field": "item_condition", "type": "string", "optional": False},
        {"field": "price_krw", "type": "int32", "optional": False},
        {"field": "regular_krw", "type": "int32", "optional": True},
        {"field": "discount_pct", "type": "int32", "optional": True},
        {"field": "price_original", "type": "double", "optional": True},
        {"field": "currency_original", "type": "string", "optional": True},
        {"field": "url", "type": "string", "optional": True},
        {"field": "collected_at", "type": "string", "optional": False},
    ],
}


def store_code(shop: dict[str, Any]) -> str:
    """ITAD shop → store 코드 (소문자 영숫자)."""
    sid = shop.get("id")
    if sid in KNOWN_SHOPS:
        return KNOWN_SHOPS[sid]
    return re.sub(r"[^a-z0-9]+", "", str(shop.get("name", "")).lower()) or f"shop{sid}"


def to_krw(amount: float | None, currency: str | None, rates: dict[str, float]) -> int | None:
    """금액을 원화 정수로. 금액이 없거나 모르는 통화면 None."""
    if amount is None or currency not in rates:
        return None
    return int(round(amount * rates[currency]))


def refine_price(
    envelope: dict[str, Any],
    resolve_game_id: Callable[[str], int | None],
    rates: dict[str, float] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """raw.price 봉투 1개 → (refined.prices payload 목록, unmatched 목록).

    deals 하나가 payload 한 줄이 된다 (스토어별 1줄).
    """
    rates = rates or DEFAULT_RATES
    payload = envelope.get("payload") or {}
    itad_id = payload.get("id")
    collected_at = envelope.get("collected_at")
    game_id = resolve_game_id(itad_id) if itad_id else None

    if game_id is None:
        return [], [
            {
                "reason": "itad_id → IGDB ID 매칭 실패",
                "source": envelope.get("source", "itad"),
                "key": itad_id,
                "collected_at": collected_at,
            }
        ]

    out: list[dict[str, Any]] = []
    unmatched: list[dict[str, Any]] = []
    for deal in payload.get("deals") or []:
        price = deal.get("price") or {}
        regular = deal.get("regular") or {}
        price_krw = to_krw(price.get("amount"), price.get("currency"), rates)
        if price_krw is None:
            unmatched.append(
                {
                    "reason": "가격 없음 또는 모르는 통화",
                    "source": "itad",
                    "key": itad_id,
                    "collected_at": collected_at,
                    "detail": {"shop": deal.get("shop"), "price": price},
                }
            )
            continue
        out.append(
            {
                "game_id": int(game_id),
                "store": store_code(deal.get("shop") or {}),
                "edition": "digital",
                "platform": "PC",
                "item_condition": "new",
                "price_krw": price_krw,
                "regular_krw": to_krw(regular.get("amount"), regular.get("currency"), rates),
                "discount_pct": deal.get("cut"),
                "price_original": price.get("amount"),
                "currency_original": price.get("currency"),
                "url": deal.get("url"),
                "collected_at": collected_at,
            }
        )
    return dedupe_by_key(out), unmatched


def price_key(row: dict[str, Any]) -> tuple[int, str, str, str, str]:
    """prices_current PK = (game_id, store, edition, platform, item_condition)."""
    return (row["game_id"], row["store"], row["edition"], row["platform"], row["item_condition"])


def dedupe_by_key(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """같은 키가 여럿이면 낮은 가격 한 줄만 (순서 유지)."""
    best: dict[tuple[int, str, str, str, str], dict[str, Any]] = {}
    for r in rows:
        k = price_key(r)
        if k not in best or r["price_krw"] < best[k]["price_krw"]:
            best[k] = r
    return list(best.values())


def message_key(row: dict[str, Any]) -> str:
    """Kafka 메시지 키 = game_id:store:edition:platform:item_condition (topics.md)."""
    return ":".join(str(v) for v in price_key(row))


def to_connect_message(row: dict[str, Any]) -> dict[str, Any]:
    """JDBC Sink가 읽는 JSON+schema 형식."""
    return {"schema": REFINED_PRICE_SCHEMA, "payload": row}
