"""한 게임 메시지가 여러 행이 되는 테이블용 정제 (Kafka 없이 시험할 수 있는 순수 함수).

토픽(= 테이블)마다 메시지 하나가 한 행이다. 필드는 erd.sql 컬럼과 같다 (AUTO_INCREMENT 제외).
형식은 docs/contracts/messages/refined.links.json 참고.

  raw.igdb game_info  → genres, game_genres, companies, game_companies, tags, game_tags,
                        game_series, game_series_map, game_platforms, game_aliases, game_store_ids
  raw.igdb time_to_beat → time_to_beat
  raw.steam player_count → player_counts
  가격 정제에 쓴 환율 → exchange_rates

ID 규칙
  - genre_id, company_id: IGDB id 그대로
  - tag_id: IGDB theme id 그대로, keyword 는 KEYWORD_TAG_OFFSET + id (두 id 체계가 겹치지 않게)
  - series_id: IGDB collection / franchise id (kind 로 구분)
"""

from __future__ import annotations

import re
from typing import Any

from refiner.rules.game import platform_release_dates

KEYWORD_TAG_OFFSET = 10_000_000
ASCII_SHORT = re.compile(r"^[A-Za-z0-9 ]{1,2}$")  # R11: 영문·숫자 2글자 이하 별칭은 잡음

# out 이름 → (필드, 타입, optional) — 이름이 곧 refined.<이름> 토픽
LINK_FIELDS: dict[str, list[tuple[str, str, bool]]] = {
    "genres": [("genre_id", "int32", False), ("name", "string", False)],
    "companies": [("company_id", "int32", False), ("name", "string", False)],
    "tags": [
        ("tag_id", "int32", False),
        ("name", "string", False),
        ("source", "string", False),
        ("name_ko", "string", True),
    ],
    "game_series": [
        ("series_id", "int64", False),
        ("kind", "string", False),
        ("name", "string", False),
    ],
    "game_genres": [("game_id", "int64", False), ("genre_id", "int32", False)],
    "game_companies": [
        ("game_id", "int64", False),
        ("company_id", "int32", False),
        ("role", "string", False),
    ],
    "game_tags": [("game_id", "int64", False), ("tag_id", "int32", False)],
    "game_series_map": [
        ("game_id", "int64", False),
        ("series_id", "int64", False),
        ("kind", "string", False),
    ],
    "game_platforms": [
        ("game_id", "int64", False),
        ("platform", "string", False),
        ("release_date", "string", True),
    ],
    "game_aliases": [
        ("game_id", "int64", False),
        ("alias", "string", False),
        ("source", "string", False),
        ("reviewed", "boolean", False),
    ],
    "game_store_ids": [
        ("game_id", "int64", False),
        ("store", "string", False),
        ("external_id", "string", False),
    ],
    "time_to_beat": [
        ("game_id", "int64", False),
        ("hastily_sec", "int32", True),
        ("normally_sec", "int32", True),
        ("completely_sec", "int32", True),
        ("ttb_count", "int32", True),
        ("updated_at", "string", False),
    ],
    "player_counts": [
        ("game_id", "int64", False),
        ("player_count", "int32", False),
        ("collected_at", "string", False),
    ],
    "exchange_rates": [
        ("rate_date", "string", False),
        ("currency", "string", False),
        ("krw_per_unit", "double", False),
    ],
}

# Kafka 메시지 키 = 테이블 PK
LINK_KEYS: dict[str, tuple[str, ...]] = {
    "genres": ("genre_id",),
    "companies": ("company_id",),
    "tags": ("tag_id",),
    "game_series": ("series_id", "kind"),
    "game_genres": ("game_id", "genre_id"),
    "game_companies": ("game_id", "company_id", "role"),
    "game_tags": ("game_id", "tag_id"),
    "game_series_map": ("game_id", "series_id", "kind"),
    "game_platforms": ("game_id", "platform"),
    "game_aliases": ("game_id", "alias"),
    "game_store_ids": ("store", "external_id"),
    "time_to_beat": ("game_id",),
    "player_counts": ("game_id", "collected_at"),
    "exchange_rates": ("rate_date", "currency"),
}

Out = tuple[str, str, dict[str, Any]]  # (out 이름, 키, Connect 메시지)


def schema(name: str) -> dict[str, Any]:
    return {
        "type": "struct",
        "name": f"refined.{name}",
        "optional": False,
        "fields": [{"field": f, "type": t, "optional": o} for f, t, o in LINK_FIELDS[name]],
    }


def message(name: str, row: dict[str, Any]) -> Out:
    """행 → (out 이름, 키, JSON+schema 메시지). 필드 순서·이름을 계약대로 맞춘다."""
    payload = {f: row.get(f) for f, _, _ in LINK_FIELDS[name]}
    key = ":".join(str(payload[k]) for k in LINK_KEYS[name])
    return name, key, {"schema": schema(name), "payload": payload}


def _items(v: Any) -> list[dict[str, Any]]:
    """IGDB 확장 필드: [{id, name}] 또는 {id, name} 하나 → 목록 (id 만 온 것은 버린다)."""
    if isinstance(v, dict):
        v = [v]
    return [x for x in (v or []) if isinstance(x, dict) and x.get("id") is not None]


def _name(x: dict[str, Any]) -> str | None:
    n = (x.get("name") or "").strip()
    return n or None


def alias_ok(alias: str) -> bool:
    """R11: 영문·숫자만으로 된 2글자 이하는 잡음이라 뺀다. 한글 2글자(몬헌·배그)는 남긴다."""
    return bool(alias) and not ASCII_SHORT.match(alias)


def game_links(row: dict[str, Any], extras: dict[str, Any], p: dict[str, Any]) -> list[Out]:
    """refined.games 한 행 + extras + IGDB payload → 연결·기준표 메시지 목록."""
    gid = int(row["game_id"])
    out: list[Out] = []

    for g in _items(p.get("genres")):
        if _name(g):
            out.append(message("genres", {"genre_id": int(g["id"]), "name": _name(g)}))
            out.append(message("game_genres", {"game_id": gid, "genre_id": int(g["id"])}))

    for ic in [x for x in p.get("involved_companies") or [] if isinstance(x, dict)]:
        c = ic.get("company")
        c = c if isinstance(c, dict) else {}
        if c.get("id") is None or not _name(c):
            continue
        cid = int(c["id"])
        roles = [r for r in ("developer", "publisher") if ic.get(r)]
        if roles:
            out.append(message("companies", {"company_id": cid, "name": _name(c)}))
        for role in roles:
            out.append(message("game_companies", {"game_id": gid, "company_id": cid, "role": role}))

    for field, source, offset in (
        ("themes", "igdb_theme", 0),
        ("keywords", "igdb_keyword", KEYWORD_TAG_OFFSET),
    ):
        for t in _items(p.get(field)):
            if not _name(t):
                continue
            tid = offset + int(t["id"])
            out.append(message("tags", {"tag_id": tid, "name": _name(t)[:64], "source": source}))
            out.append(message("game_tags", {"game_id": gid, "tag_id": tid}))

    for field, kind in (
        ("collections", "collection"),
        ("collection", "collection"),
        ("franchises", "franchise"),
        ("franchise", "franchise"),
    ):
        for s in _items(p.get(field)):
            if not _name(s):
                continue
            sid = int(s["id"])
            out.append(message("game_series", {"series_id": sid, "kind": kind, "name": _name(s)}))
            out.append(message("game_series_map", {"game_id": gid, "series_id": sid, "kind": kind}))

    dates = extras.get("platform_release_dates") or platform_release_dates(p)
    for platform in extras.get("platforms") or []:
        out.append(
            message(
                "game_platforms",
                {"game_id": gid, "platform": platform, "release_date": dates.get(platform)},
            )
        )

    seen: set[str] = set()
    names = [row.get("name"), row.get("name_ko")]
    names += [a.get("name") for a in _items(p.get("alternative_names"))]
    for n in names:
        alias = (n or "").strip()[:255]
        if alias_ok(alias) and alias not in seen:
            seen.add(alias)
            out.append(
                message(
                    "game_aliases",
                    {"game_id": gid, "alias": alias, "source": "igdb", "reviewed": False},
                )
            )

    for store, ext_id in extras.get("store_ids") or []:
        out.append(
            message("game_store_ids", {"game_id": gid, "store": store, "external_id": str(ext_id)})
        )
    return out


def _int(v: Any) -> int | None:
    try:
        return None if v is None else int(v)
    except (TypeError, ValueError):
        return None


def refine_time_to_beat(envelope: dict[str, Any]) -> tuple[list[Out], list[dict[str, Any]]]:
    """raw.igdb time_to_beat → refined.time_to_beat. payload 는 IGDB game_time_to_beats 응답
    (목록 또는 한 건). 값은 초 단위 그대로. game_id 는 IGDB 게임 id = 기준 ID."""
    payload = envelope.get("payload")
    items = payload if isinstance(payload, list) else [payload or {}]
    at = envelope.get("collected_at")
    out: list[Out] = []
    unmatched: list[dict[str, Any]] = []
    for t in items:
        gid = _int(t.get("game_id"))
        if gid is None:
            unmatched.append(
                {
                    "reason": "time_to_beat 에 game_id 없음",
                    "source": "igdb",
                    "key": t.get("id"),
                    "collected_at": at,
                }
            )
            continue
        out.append(
            message(
                "time_to_beat",
                {
                    "game_id": gid,
                    "hastily_sec": _int(t.get("hastily")),
                    "normally_sec": _int(t.get("normally")),
                    "completely_sec": _int(t.get("completely")),
                    "ttb_count": _int(t.get("count")),
                    "updated_at": at,
                },
            )
        )
    return out, unmatched


def refine_player_count(
    envelope: dict[str, Any], appid: int | None, resolve_steam: Any
) -> tuple[list[Out], list[dict[str, Any]]]:
    """raw.steam player_count (GetNumberOfCurrentPlayers) → refined.player_counts."""
    p = envelope.get("payload") or {}
    resp = p.get("response") if isinstance(p.get("response"), dict) else p
    at = envelope.get("collected_at")
    count = _int(resp.get("player_count"))
    gid = resolve_steam(appid) if appid is not None else None
    if count is None or resp.get("result", 1) != 1:
        return [], [
            {
                "reason": "동접자 수 없음 (result != 1)",
                "source": "steam",
                "key": appid,
                "collected_at": at,
            }
        ]
    if gid is None:
        return [], [
            {
                "reason": "steam appid → IGDB ID 매칭 실패",
                "source": "steam",
                "key": appid,
                "collected_at": at,
            }
        ]
    return [
        message("player_counts", {"game_id": gid, "player_count": count, "collected_at": at})
    ], []


def exchange_rate_rows(collected_at: str | None, rates: dict[str, float]) -> list[Out]:
    """가격 정제에 쓴 환율 → refined.exchange_rates (원화 제외). 날짜는 수집 시각(UTC)의 날짜."""
    if not collected_at:
        return []
    day = collected_at[:10]
    return [
        message("exchange_rates", {"rate_date": day, "currency": cur, "krw_per_unit": float(v)})
        for cur, v in sorted(rates.items())
        if cur != "KRW"
    ]
