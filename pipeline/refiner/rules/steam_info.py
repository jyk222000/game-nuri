"""raw.steam(app_details) → refined.games_steam. 순수 함수.

games 테이블 칼럼 중 Steam 에서만 오는 3개를 뽑는다
(docs/contracts/messages/refined.games_steam.json).
  age_rating       required_age → 정수 (0 = 제한 없음). "18", 18, "18+" 모두 18
  korean_supported supported_languages 에 Korean / 한국어 가 있으면 True
  is_online        categories 에 온라인 멀티(ONLINE_CATEGORIES)가 하나라도 있으면 True
원본에 항목 자체가 없으면 None (모름).
게임 매칭 실패는 requirements 쪽에서 이미 알리므로 여기선 조용히 넘긴다.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from refiner.rules.requirements import _unwrap

# Steam category id: 1 멀티플레이어, 20 MMO, 27 크로스 플랫폼 멀티, 36 온라인 PvP, 38 온라인 협동
# (24·37·39 화면 분할·로컬 협동은 온라인이 아니라 뺀다)
ONLINE_CATEGORIES = {1, 20, 27, 36, 38}

REFINED_GAME_STEAM_SCHEMA: dict[str, Any] = {
    "type": "struct",
    "name": "refined_game_steam",
    "fields": [
        {"field": "game_id", "type": "int64", "optional": False},
        {"field": "age_rating", "type": "int16", "optional": True},
        {"field": "korean_supported", "type": "boolean", "optional": True},
        {"field": "is_online", "type": "boolean", "optional": True},
        {"field": "updated_at", "type": "string", "optional": False},
    ],
}


def age_rating(v: Any) -> int | None:
    if v is None or isinstance(v, bool):
        return None
    m = re.search(r"\d+", str(v))
    return int(m.group()) if m else None


def korean_supported(v: Any) -> bool | None:
    if not isinstance(v, str):
        return None
    return bool(re.search(r"korean|한국어", v, re.IGNORECASE))


def is_online(categories: Any) -> bool | None:
    if not isinstance(categories, list):
        return None
    ids = {c.get("id") for c in categories if isinstance(c, dict)}
    return bool(ids & ONLINE_CATEGORIES)


def refine_steam_info(
    envelope: dict[str, Any], resolve_game_id: Callable[[int], int | None]
) -> list[dict[str, Any]]:
    appid, data = _unwrap(envelope.get("payload") or {})
    if appid is None:
        appid = data.get("steam_appid")
    game_id = resolve_game_id(int(appid)) if appid is not None else None
    if game_id is None or not data:
        return []
    row = {
        "game_id": int(game_id),
        "age_rating": age_rating(data.get("required_age")),
        "korean_supported": korean_supported(data.get("supported_languages")),
        "is_online": is_online(data.get("categories")),
        "updated_at": envelope.get("collected_at"),
    }
    if row["age_rating"] is None and row["korean_supported"] is None and row["is_online"] is None:
        return []
    return [row]


def message_key(row: dict[str, Any]) -> str:
    return str(row["game_id"])


def to_connect_message(row: dict[str, Any]) -> dict[str, Any]:
    return {"schema": REFINED_GAME_STEAM_SCHEMA, "payload": row}
