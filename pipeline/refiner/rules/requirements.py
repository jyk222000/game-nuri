"""raw.steam(app_details) → refined.requirements. 순수 함수.

입력 payload 는 Steam appdetails 응답. 두 모양을 모두 받는다.
  {"steam_appid": 1245620, "data": {... pc_requirements ...}}
  {"1245620": {"success": true, "data": {...}}}
Steam appid → IGDB game_id 대응은 resolve_game_id 로 받는다.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

LABEL = {
    "운영 체제": "OS",
    "프로세서": "CPU",
    "메모리": "RAM",
    "그래픽": "GPU",
    "저장 공간": "Storage",
    "DirectX": "DirectX",
    "OS": "OS",
    "Processor": "CPU",
    "Memory": "RAM",
    "Graphics": "GPU",
    "Storage": "Storage",
}

REFINED_REQUIREMENTS_SCHEMA: dict[str, Any] = {
    "type": "struct",
    "name": "refined_requirements",
    "fields": [
        {"field": "game_id", "type": "int64", "optional": False},
        {"field": "minimum_text", "type": "string", "optional": True},
        {"field": "recommended_text", "type": "string", "optional": True},
        {"field": "updated_at", "type": "string", "optional": False},
    ],
}


def html_to_text(html: Any) -> str | None:
    """Steam 사양 HTML → 'OS: … / CPU: … / RAM: … / GPU: …' (R08). 없으면 None (R01)."""
    if not isinstance(html, str) or not html.strip():
        return None
    text = re.sub(r"<br\s*/?>|</li>", "\n", html)
    text = re.sub(r"<[^>]+>", "", text)
    parts = []
    for line in text.split("\n"):
        m = re.match(r"\s*([^:]+?)\s*\*?\s*:\s*(.+)", line)
        if m and m.group(1).strip() in LABEL:
            parts.append(f"{LABEL[m.group(1).strip()]}: {m.group(2).strip()}")
    return " / ".join(parts) or None


def _unwrap(payload: dict[str, Any]) -> tuple[Any, dict[str, Any]]:
    if "data" in payload:
        return payload.get("steam_appid"), payload.get("data") or {}
    for k, v in payload.items():
        if str(k).isdigit() and isinstance(v, dict):
            return int(k), v.get("data") or {}
    return None, {}


def refine_requirements(
    envelope: dict[str, Any], resolve_game_id: Callable[[int], int | None]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    appid, data = _unwrap(envelope.get("payload") or {})
    if appid is None:
        appid = data.get("steam_appid")
    collected_at = envelope.get("collected_at")
    game_id = resolve_game_id(int(appid)) if appid is not None else None
    if game_id is None:
        return [], [
            {
                "reason": "Steam appid → IGDB ID 매칭 실패",
                "source": "steam",
                "key": appid,
                "collected_at": collected_at,
            }
        ]
    req = data.get("pc_requirements")
    if (
        not isinstance(req, dict) or not req
    ):  # 콘솔 전용 게임 등: 사양이 없는 건 정상이라 행을 만들지 않는다
        return [], []
    minimum, recommended = html_to_text(req.get("minimum")), html_to_text(req.get("recommended"))
    if minimum is None and recommended is None:
        return [], []
    return [
        {
            "game_id": int(game_id),
            "minimum_text": minimum,
            "recommended_text": recommended,
            "updated_at": collected_at,
        }
    ], []


def message_key(row: dict[str, Any]) -> str:
    return str(row["game_id"])


def to_connect_message(row: dict[str, Any]) -> dict[str, Any]:
    return {"schema": REFINED_REQUIREMENTS_SCHEMA, "payload": row}
