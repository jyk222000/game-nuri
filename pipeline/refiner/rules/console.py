"""raw.console(다나와) → refined.prices. 순수 함수.

키 = (game_id, store, edition, platform, item_condition).
같은 게임의 PS4·PS5, 신품·중고를 따로 싣는다.
platform 은 platform_hint, 없으면 상품명에서 찾는다. 못 찾으면 unmatched.
item_condition 은 condition(new|used), 없으면 new.
거르기(비게임·본체 번들·해외판·DLC·리마스터)와 상품명 매칭은 rules/danawa_match.py.

같은 키(게임·플랫폼·상태·매체)에 상품이 여러 개면 한 수집 회차 안에서 아래 순서로 하나만 남긴다
(ConsoleBest, #93). DB 는 upsert 라 마지막에 보낸 줄이 남으므로 '더 나은 것'만 보낸다.
  1) 본편이 에디션보다 우선 (에디션 가격이 본편 최저가를 왜곡하지 않게)
  2) 같은 종류끼리는 더 싼 것
본편이 없는 플랫폼(예: 사이버펑크 2077 PS5 = 얼티밋 에디션만)은 에디션 최저가가 들어간다.
상품명 매칭이 실패하면 수집 때 검색한 게임(request.params.igdb_id)을,
상품명에 검색어가 있을 때만 쓴다.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from refiner.rules.danawa_match import EDITION_REASON, TitleMatcher, exclude_reason, hint_match
from refiner.rules.normalize_title import normalize_title
from refiner.rules.price import REFINED_PRICE_SCHEMA  # noqa: F401  (같은 schema)

EDITIONS = {"digital", "physical", "code"}
MEDIUM_TO_EDITION = {"disc": "physical", "cartridge": "physical", "code": "code"}
PLATFORMS = {"PC", "PS4", "PS5", "Switch", "Switch2", "XboxOne", "XboxSeries"}
# 상품명 → 플랫폼 (앞에 있는 것부터 검사: 스위치2를 스위치보다 먼저)
TITLE_PLATFORM = [
    (re.compile(r"PS5|플레이스테이션\s*5|플스\s*5", re.I), "PS5"),
    (re.compile(r"PS4|플레이스테이션\s*4|플스\s*4", re.I), "PS4"),
    (re.compile(r"스위치\s*2|Switch\s*2|NS2\b", re.I), "Switch2"),
    (re.compile(r"스위치|Switch|닌텐도|\bNSW?\b", re.I), "Switch"),
    (
        re.compile(r"Xbox\s*Series|XSX|엑스박스\s*(시리즈|Series)|XBOX\s*X\s*[|/]\s*S", re.I),
        "XboxSeries",
    ),
    (re.compile(r"Xbox\s*One|XB1|엑스박스\s*원", re.I), "XboxOne"),
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


def _when(s: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None


class ConsoleBest:
    """키별로 이번 수집 회차에서 가장 나은 상품 (본편 > 에디션, 같은 종류는 더 싼 것).

    수집기는 6시간마다 돈다. 마지막으로 본 지 CYCLE 이 지나면 새 회차로 보고 처음부터 고른다.
    메모리에만 둔다 (재시작하면 새 회차부터, 결과는 같은 규칙으로 다시 맞춰진다).
    """

    CYCLE = timedelta(hours=3)

    def __init__(self) -> None:
        self.best: dict[
            tuple, tuple[bool, int, datetime]
        ] = {}  # key → (에디션?, 가격, 마지막 본 시각)

    def offer(self, key: tuple, is_edition: bool, price: int, when: datetime | None) -> bool:
        """이 상품을 보낼지 (지금까지 중 가장 나으면 True 를 돌려주고 기억)."""
        when = when or datetime.min
        prev = self.best.get(key)
        if prev is not None and when - prev[2] <= self.CYCLE:
            better = (is_edition, price) < (prev[0], prev[1])  # False(본편) 가 먼저
            self.best[key] = (prev[0], prev[1], max(when, prev[2]))
            if not better:
                return False
        self.best[key] = (is_edition, price, when)
        return True


def refine_console_price(
    envelope: dict[str, Any],
    resolve_game_id: Callable[[str], int | None],
    matcher: TitleMatcher | None = None,
    best: ConsoleBest | None = None,
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
    is_edition = reason == EDITION_REASON
    if reason and not is_edition:
        return unmatched(reason)
    price = p.get("lowest_price")
    if not isinstance(price, (int, float)) or price <= 0:
        return unmatched("가격 없음")
    platform = infer_platform(p)
    if platform is None:
        return unmatched("플랫폼을 알 수 없음")
    condition = p.get("condition") if p.get("condition") in ("new", "used") else "new"
    params = (envelope.get("request") or {}).get("params") or {}
    game_id = resolve_game_id(normalize_title(title))
    why = "상품명 → IGDB ID 매칭 실패"
    if game_id is None and matcher is not None:
        game_id, why = matcher.match(title)
    # 별칭에 없는 표기: 검색어가 상품명에 있으면 수집 때 검색한 게임으로 본다
    if (
        game_id is None
        and why.endswith("매칭 실패")
        and params.get("igdb_id")
        and hint_match(title, params.get("query"))
    ):
        game_id = int(params["igdb_id"])
    if game_id is None:
        return unmatched(why)
    edition = infer_edition(p)
    if best is not None:
        key = (int(game_id), edition, platform, condition)
        if not best.offer(key, is_edition, int(price), _when(collected_at)):
            # 에디션은 이유를 남기고, 같은 종류의 더 비싼 상품은 실패가 아니라 조용히 넘긴다
            return unmatched("에디션 (본편 있음)") if is_edition else ([], [])
    elif is_edition:
        return unmatched(EDITION_REASON)
    return [
        {
            "game_id": int(game_id),
            "store": "danawa",
            "edition": edition,
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
