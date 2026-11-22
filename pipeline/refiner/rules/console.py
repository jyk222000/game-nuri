"""raw.console(다나와) → refined.prices. 순수 함수.

계약 키가 (game_id, store, edition)뿐이라 플랫폼·신품/중고를 담지 못한다.
그래서 이 규칙은 '신품' 가격만 보내고, 같은 게임·같은 에디션이 여러 플랫폼이면 메시지 단위로는
구분할 수 없다 (나중에 온 메시지가 덮어쓴다).
해결은 contracts 에 platform·item_condition 추가 (변경 제안 1번).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from refiner.rules.normalize_title import normalize_title
from refiner.rules.price import REFINED_PRICE_SCHEMA  # noqa: F401  (같은 schema)

EDITIONS = {"digital", "physical", "code"}
MEDIUM_TO_EDITION = {"disc": "physical", "cartridge": "physical", "code": "code"}
OVERSEAS = re.compile(r"일본발매|해외|EU 버전|북미|\[호환\]|호환")  # R11


def infer_edition(payload: dict[str, Any]) -> str:
    """edition 이 비어 있으면 상품명으로 추정 (R07)."""
    ed = payload.get("edition")
    if ed in EDITIONS:
        return ed
    ed = MEDIUM_TO_EDITION.get(payload.get("medium"))
    if ed:
        return ed
    if re.search(r"코드|스팀|steam|key|문자전송|다운로드", payload.get("product_name") or "", re.I):
        return "code"
    return "code" if payload.get("platform_hint") == "PC" else "physical"


def refine_console_price(
    envelope: dict[str, Any], resolve_game_id: Callable[[str], int | None]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    p = envelope.get("payload") or {}
    collected_at = envelope.get("collected_at")
    title = p.get("product_name") or ""

    def unmatched(reason: str) -> tuple[list, list]:
        return [], [
            {
                "reason": reason,
                "source": "danawa",
                "key": p.get("pcode"),
                "title": title,
                "collected_at": collected_at,
            }
        ]

    if OVERSEAS.search(title):
        return unmatched("해외판·호환판 표기")
    price = p.get("lowest_price")
    if not isinstance(price, (int, float)) or price <= 0:
        return unmatched("가격 없음")
    if p.get("condition") == "used":  # 계약 키에 신품/중고 칸이 없어 중고는 싣지 못한다
        return unmatched("중고 가격은 계약 키에 칸이 없음")
    game_id = resolve_game_id(normalize_title(title))
    if game_id is None:
        return unmatched("상품명 → IGDB ID 매칭 실패")
    return [
        {
            "game_id": int(game_id),
            "store": "danawa",
            "edition": infer_edition(p),
            "price_krw": int(price),
            "regular_krw": None,
            "discount_pct": None,
            "price_original": float(price),
            "currency_original": "KRW",
            "url": p.get("url"),
            "collected_at": collected_at,
        }
    ], []
