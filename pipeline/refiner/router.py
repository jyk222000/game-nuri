"""봉투 하나를 kind 에 따라 알맞은 정제 규칙으로 보낸다 (순수 함수, Kafka 없음)."""

from __future__ import annotations

from typing import Any

from refiner.rules import console, game, requirements
from refiner.rules import price as price_rules

# 출력 이름 → (환경변수로 바꿀 수 있는) 기본 토픽
OUT_TOPICS = {
    "prices": "refined.prices",
    "games": "refined.games",
    "requirements": "refined.requirements",
    "unmatched": "refined.unmatched",
}


class Maps:
    """매칭용 대응표. 운영 방식(game_store_ids 등)이 정해질 때까지의 임시 JSON 파일.

    {"itad": {itad_id: game_id}, "steam": {steam_appid: game_id},
    "alias": {정규화한 상품명: game_id}}
    (예전 모양인 {itad_id: game_id} 하나짜리도 읽는다)
    """

    def __init__(self, data: dict[str, Any] | None = None):
        data = data or {}
        if data and not set(data) <= {"itad", "steam", "alias"}:
            data = {"itad": data}
        self.itad = {k: int(v) for k, v in (data.get("itad") or {}).items()}
        self.steam = {int(k): int(v) for k, v in (data.get("steam") or {}).items()}
        self.alias = {k: int(v) for k, v in (data.get("alias") or {}).items()}

    def size(self) -> str:
        return f"itad {len(self.itad)}, steam {len(self.steam)}, alias {len(self.alias)}"


def route(envelope: dict[str, Any], maps: Maps) -> dict[str, Any]:
    """→ {"out": [(out_name, key, message)], "unmatched": [...], "extras": {...},
    "ignored": bool}"""
    kind = envelope.get("kind")
    out: list[tuple[str, str, dict[str, Any]]] = []
    unmatched: list[dict[str, Any]] = []
    extras: dict[str, Any] = {}

    if kind in ("price", "console_price"):
        if kind == "price":
            rows, unmatched = price_rules.refine_price(envelope, maps.itad.get)
        else:
            rows, unmatched = console.refine_console_price(envelope, maps.alias.get)
        out = [
            ("prices", price_rules.message_key(r), price_rules.to_connect_message(r)) for r in rows
        ]
    elif kind == "game_info":
        rows, extras, unmatched = game.refine_game(envelope)
        out = [("games", game.message_key(r), game.to_connect_message(r)) for r in rows]
    elif kind == "app_details":
        rows, unmatched = requirements.refine_requirements(envelope, maps.steam.get)
        out = [
            ("requirements", requirements.message_key(r), requirements.to_connect_message(r))
            for r in rows
        ]
    else:  # review, owned_games, player_count, time_to_beat 등: 아직 정제 규칙이 없다
        return {"out": [], "unmatched": [], "extras": {}, "ignored": True}
    return {"out": out, "unmatched": unmatched, "extras": extras, "ignored": False}
