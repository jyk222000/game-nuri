"""봉투 하나를 kind 에 따라 알맞은 정제 규칙으로 보낸다 (순수 함수, Kafka 없음)."""

from __future__ import annotations

from typing import Any

from refiner.rules import console, game, links, requirements
from refiner.rules import price as price_rules
from refiner.rules.normalize_title import normalize_title

# 출력 이름 → (환경변수로 바꿀 수 있는) 기본 토픽
OUT_TOPICS = {
    "prices": "refined.prices",
    "games": "refined.games",
    "requirements": "refined.requirements",
    "unmatched": "refined.unmatched",
    # 한 게임이 여러 행이 되는 테이블 (rules/links.py, 토픽 이름 = refined.<이름>)
    **{name: f"refined.{name}" for name in links.LINK_FIELDS},
}


class Maps:
    """매칭용 대응표 (game_id = IGDB ID).

    {"itad": {itad_id: game_id}, "steam": {steam_appid: game_id},
    "alias": {정규화한 상품명: game_id}}
    (예전 모양인 {itad_id: game_id} 하나짜리도 읽는다)

    시작할 때 JSON 파일로 채우고, 처리하면서 스스로 배운다 (learn_*):
      - raw.igdb 게임 정보 → steam appid, 게임 이름·한글 이름(별칭)
      - raw.price 에 steam appid 힌트가 있으면 → itad_id
    배운 내용은 changed 가 True 가 되고, main 이 상태 파일에 저장한다.
    """

    def __init__(self, data: dict[str, Any] | None = None):
        data = data or {}
        if data and not set(data) <= {"itad", "steam", "alias"}:
            data = {"itad": data}
        self.itad = {k: int(v) for k, v in (data.get("itad") or {}).items()}
        self.steam = {int(k): int(v) for k, v in (data.get("steam") or {}).items()}
        self.alias = {k: int(v) for k, v in (data.get("alias") or {}).items()}
        self.changed = False
        self.sent_rates: set[str] = set()  # 이번 실행에서 이미 보낸 환율 날짜 (저장 안 함)

    def size(self) -> str:
        return f"itad {len(self.itad)}, steam {len(self.steam)}, alias {len(self.alias)}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "itad": dict(sorted(self.itad.items())),
            "steam": {str(k): v for k, v in sorted(self.steam.items())},
            "alias": dict(sorted(self.alias.items())),
        }

    def merge(self, other: Maps) -> None:
        """다른 대응표를 덧붙인다. 이미 있는 값은 바꾸지 않는다 (먼저 읽은 파일이 우선)."""
        for mine, theirs in ((self.itad, other.itad), (self.steam, other.steam)):
            for k, v in theirs.items():
                mine.setdefault(k, v)
        for k, v in other.alias.items():
            self.alias.setdefault(k, v)

    def _put(self, table: dict[Any, int], key: Any, game_id: int) -> None:
        if key in (None, "") or key in table:  # 이미 있는 값은 덮어쓰지 않는다 (충돌 방지)
            return
        table[key] = game_id
        self.changed = True

    def learn_from_game(self, row: dict[str, Any], extras: dict[str, Any]) -> None:
        """refined.games 한 행 + extras → steam appid, 이름 별칭을 배운다."""
        gid = int(row["game_id"])
        for store, ext_id in extras.get("store_ids") or []:
            if store == "steam" and str(ext_id).isdigit():
                self._put(self.steam, int(ext_id), gid)
        for name in (row.get("name"), row.get("name_ko")):
            if name:
                self._put(self.alias, normalize_title(name), gid)

    def resolve_itad(self, itad_id: str | None, steam_hint: int | None) -> int | None:
        """itad_id → game_id. 모르면 steam appid 힌트로 찾고, 찾으면 itad_id 를 배운다."""
        if itad_id and itad_id in self.itad:
            return self.itad[itad_id]
        gid = self.steam.get(steam_hint) if steam_hint is not None else None
        if gid is not None and itad_id:
            self._put(self.itad, itad_id, gid)
        return gid


def steam_hint(envelope: dict[str, Any]) -> int | None:
    """raw.price 봉투에서 Steam appid 힌트를 찾는다 (수집기가 lookup 에 쓴 appid).

    찾는 곳: payload.steam_appid, request.params.steam_appid / appid
    """
    payload = envelope.get("payload") or {}
    params = (envelope.get("request") or {}).get("params") or {}
    for v in (payload.get("steam_appid"), params.get("steam_appid"), params.get("appid")):
        s = str(v).removeprefix("app/") if v is not None else ""
        if s.isdigit():
            return int(s)
    return None


def route(envelope: dict[str, Any], maps: Maps) -> dict[str, Any]:
    """→ {"out": [(out_name, key, message)], "unmatched": [...], "extras": {...},
    "ignored": bool}"""
    kind = envelope.get("kind")
    out: list[tuple[str, str, dict[str, Any]]] = []
    unmatched: list[dict[str, Any]] = []
    extras: dict[str, Any] = {}

    if kind in ("price", "console_price"):
        if kind == "price":
            hint = steam_hint(envelope)
            itad_id = (envelope.get("payload") or {}).get("id")
            known = itad_id in maps.itad
            rows, unmatched = price_rules.refine_price(
                envelope, lambda i: maps.resolve_itad(i, hint)
            )
            if rows and itad_id and not known:  # 새로 배운 ITAD id → game_store_ids
                out.append(
                    links.message(
                        "game_store_ids",
                        {"game_id": rows[0]["game_id"], "store": "itad", "external_id": itad_id},
                    )
                )
            day = (envelope.get("collected_at") or "")[:10]
            if rows and day and day not in maps.sent_rates:
                maps.sent_rates.add(day)
                out += links.exchange_rate_rows(
                    envelope.get("collected_at"), price_rules.DEFAULT_RATES
                )
        else:
            rows, unmatched = console.refine_console_price(envelope, maps.alias.get)
            pcode = (envelope.get("payload") or {}).get("pcode")
            if rows and pcode:
                out.append(
                    links.message(
                        "game_store_ids",
                        {
                            "game_id": rows[0]["game_id"],
                            "store": "danawa",
                            "external_id": str(pcode),
                        },
                    )
                )
        out = [
            ("prices", price_rules.message_key(r), price_rules.to_connect_message(r)) for r in rows
        ] + out
    elif kind == "game_info":
        rows, extras, unmatched = game.refine_game(envelope)
        payload = envelope.get("payload") or {}
        for r in rows:
            maps.learn_from_game(r, extras)
            out.append(("games", game.message_key(r), game.to_connect_message(r)))
            out += links.game_links(r, extras, payload)
    elif kind == "app_details":
        rows, unmatched = requirements.refine_requirements(envelope, maps.steam.get)
        out = [
            ("requirements", requirements.message_key(r), requirements.to_connect_message(r))
            for r in rows
        ]
    elif kind == "time_to_beat":
        out, unmatched = links.refine_time_to_beat(envelope)
    elif kind == "player_count":
        out, unmatched = links.refine_player_count(envelope, steam_hint(envelope), maps.steam.get)
    else:  # review, owned_games 등: 아직 정제 규칙이 없다
        return {"out": [], "unmatched": [], "extras": {}, "ignored": True}
    return {"out": out, "unmatched": unmatched, "extras": extras, "ignored": False}
