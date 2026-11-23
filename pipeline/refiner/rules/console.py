"""raw.console(다나와) → refined.prices. 순수 함수.

키 = (game_id, store, edition, platform, item_condition).
같은 게임의 PS4·PS5, 신품·중고를 따로 싣는다.
platform 은 platform_hint, 없으면 상품명에서 찾는다. 못 찾으면 unmatched.
item_condition 은 condition(new|used), 없으면 new.
거르기(비게임·본체 번들·해외판·DLC·에디션)와 상품명 매칭은 rules/danawa_match.py.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from refiner.rules.danawa_match import TitleMatcher, exclude_reason
from refiner.rules.normalize_title import normalize_title
from refiner.rules.price import REFINED_PRICE_SCHEMA  # noqa: F401  (같은 schema)

EDITIONS = {"digital", "physical", "code"}
MEDIUM_TO_EDITION = {"disc": "physical", "cartridge": "physical", "code": "code"}
PLATFORMS = {"PC", "PS4", "PS5", "Switch", "Switch2", "XboxOne", "XboxSeries"}
# 상품명 → 플랫폼 (앞에 있는 것부터 검사: 스위치2를 스위치보다 먼저)
TITLE_PLATFORM = [
    (re.compile(r"PS5|플레이스테이션\s*5", re.I), "PS5"),
    (re.compile(r"PS4|플레이스테이션\s*4", re.I), "PS4"),
    (re.compile(r"스위치\s*2|Switch\s*2", re.I), "Switch2"),
    (re.compile(r"스위치|Switch|닌텐도", re.I), "Switch"),
    (re.compile(r"Xbox\s*Series|XSX", re.I), "XboxSeries"),
    (re.compile(r"Xbox\s*One|XB1", re.I), "XboxOne"),
    (re.compile(r"\bPC\b|스팀|Steam", re.I), "PC"),
]


def infer_platform(payload: dict[str, Any]) -> str | None:
    """platform_hint 가 서비스 플랫폼이면 그대로, 아니면 상품명에서 찾는다."""
    hint = payload.get("platform_hint")
    if hint in PLATFORMS:
        return hint
    title = payload.get("product_name") or ""
    for pattern, key in TITLE_PLATFORM:
        if pattern.search(title):
            return key
    return None


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
    envelope: dict[str, Any],
    resolve_game_id: Callable[[str], int | None],
    matcher: TitleMatcher | None = None,
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

    reason = exclude_reason(title)
    if reason:
        return unmatched(reason)
    price = p.get("lowest_price")
    if not isinstance(price, (int, float)) or price <= 0:
        return unmatched("가격 없음")
    platform = infer_platform(p)
    if platform is None:
        return unmatched("플랫폼을 알 수 없음")
    condition = p.get("condition") if p.get("condition") in ("new", "used") else "new"
    game_id = resolve_game_id(normalize_title(title))
    if game_id is None and matcher is not None:
        game_id, why = matcher.match(title)
        if game_id is None:
            return unmatched(why)
    if game_id is None:
        return unmatched("상품명 → IGDB ID 매칭 실패")
    return [
        {
            "game_id": int(game_id),
            "store": "danawa",
            "edition": infer_edition(p),
            "platform": platform,
            "item_condition": condition,
            "price_krw": int(price),
            "regular_krw": None,
            "discount_pct": None,
            "price_original": float(price),
            "currency_original": "KRW",
            "url": p.get("url"),
            "collected_at": collected_at,
        }
    ], []
