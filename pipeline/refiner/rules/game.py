"""raw.igdb(game_info) → refined.games. Kafka 없이 테스트할 수 있는 순수 함수.

입력 payload = IGDB /games 응답 한 건 (id, name, first_release_date, slug, summary, game_type,
parent_game, version_parent, cover, total_rating, total_rating_count, aggregated_rating,
aggregated_rating_count, platforms, release_dates, external_games, localizations).
games 테이블 컬럼 중 Steam 에서 오는 age_rating·korean_supported·is_online 은 이 메시지에 없으므로
None 이다 (Steam 쪽 메시지와 합치는 방법은 팀 결정 필요: README 참고).
"""

from __future__ import annotations

import datetime
from typing import Any

IGDB_PLATFORM: dict[str, str] = {
    "PC (Microsoft Windows)": "PC",
    "PlayStation 5": "PS5",
    "PlayStation 4": "PS4",
    "Nintendo Switch": "Switch",
    "Nintendo Switch 2": "Switch2",
    "Xbox Series X|S": "XboxSeries",
    "Xbox One": "XboxOne",
}
STEAM_SOURCE = 1  # IGDB external_game_source: Steam
COVER_URL = "https://images.igdb.com/igdb/image/upload/t_cover_big/%s.jpg"

REFINED_GAME_FIELDS = [
    ("game_id", "int64", False),
    ("name", "string", False),
    ("name_ko", "string", True),
    ("slug", "string", True),
    ("summary", "string", True),
    ("release_date", "string", True),
    ("game_type", "int16", True),
    ("parent_game_id", "int64", True),
    ("version_parent_id", "int64", True),
    ("cover_image_id", "string", True),
    ("cover_url", "string", True),
    ("rating", "double", True),
    ("rating_count", "int32", True),
    ("aggregated_rating", "double", True),
    ("aggregated_rating_count", "int32", True),
    ("age_rating", "int16", True),
    ("korean_supported", "boolean", True),
    ("is_online", "boolean", True),
    ("updated_at", "string", False),
]
REFINED_GAME_SCHEMA: dict[str, Any] = {
    "type": "struct",
    "name": "refined_game",
    "fields": [{"field": f, "type": t, "optional": o} for f, t, o in REFINED_GAME_FIELDS],
}


def _blank(v: Any) -> Any:
    """빈 문자열은 NULL (R01)."""
    return None if isinstance(v, str) and not v.strip() else v


def _ref_id(v: Any) -> int | None:
    """IGDB 참조는 숫자 또는 {id: 숫자}. 둘 다 받는다."""
    if isinstance(v, dict):
        v = v.get("id")
    return int(v) if v is not None else None


def unix_to_date(sec: Any) -> str | None:
    """유닉스 초 → 'YYYY-MM-DD' (R03)."""
    if sec is None:
        return None
    return (datetime.datetime(1970, 1, 1) + datetime.timedelta(seconds=int(sec))).strftime(
        "%Y-%m-%d"
    )


def korean_name(payload: dict[str, Any]) -> str | None:
    for loc in payload.get("localizations") or payload.get("game_localizations") or []:
        if (loc.get("region") or {}).get("name") == "Korea" and _blank(loc.get("name")):
            return loc["name"]
    return None


def refine_game(
    envelope: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
    """raw.igdb 봉투 1개 → (refined.games payload 목록, 부가 정보, unmatched).

    부가 정보(extras)는 한 메시지가 여러 행이 되는 것들이다.
    토픽을 나눌지 정해질 때까지 발행하지 않는다.
      platforms  : 내부 플랫폼 키 목록 (R07), skipped: 서비스 대상이 아닌 플랫폼 이름
      store_ids  : [(store, external_id)] — Steam appid 등 (게임 ID 통합용)
    """
    p = envelope.get("payload") or {}
    if p.get("id") is None or not _blank(p.get("name")):
        return (
            [],
            {},
            [
                {
                    "reason": "IGDB id 또는 name 없음",
                    "source": "igdb",
                    "key": p.get("id"),
                    "collected_at": envelope.get("collected_at"),
                }
            ],
        )
    cover = p.get("cover") or {}
    image_id = _blank(cover.get("image_id"))
    rating = p.get("total_rating")
    agg = p.get("aggregated_rating")
    row = {
        "game_id": int(p["id"]),
        "name": p["name"],
        "name_ko": korean_name(p),
        "slug": _blank(p.get("slug")),
        "summary": _blank(p.get("summary")),
        "release_date": unix_to_date(p.get("first_release_date")),
        "game_type": _ref_id(p.get("game_type")),
        "parent_game_id": _ref_id(p.get("parent_game")),
        "version_parent_id": _ref_id(p.get("version_parent")),
        "cover_image_id": image_id,
        "cover_url": (COVER_URL % image_id) if image_id else None,
        "rating": round(rating, 2) if rating is not None else None,
        "rating_count": p.get("total_rating_count"),
        "aggregated_rating": round(agg, 2) if agg is not None else None,
        "aggregated_rating_count": p.get("aggregated_rating_count"),
        "age_rating": None,
        "korean_supported": None,
        "is_online": None,
        "updated_at": envelope.get("collected_at"),
    }
    platforms, skipped = [], []
    for pl in p.get("platforms") or []:
        key = IGDB_PLATFORM.get(pl.get("name"))
        if key is None:
            skipped.append(pl.get("name"))
        elif key not in platforms:
            platforms.append(key)
    store_ids = [
        ("steam", str(e["uid"]))
        for e in p.get("external_games") or []
        if e.get("external_game_source") == STEAM_SOURCE and e.get("uid")
    ]
    extras = {
        "platforms": platforms,
        "skipped_platforms": skipped,
        "store_ids": store_ids,
        "platform_release_dates": platform_release_dates(p),
    }
    return [row], extras, []


def platform_release_dates(p: dict[str, Any]) -> dict[str, str]:
    """IGDB release_dates → {플랫폼 키: 가장 빠른 출시일} (game_platforms.release_date)."""
    out: dict[str, str] = {}
    for rd in p.get("release_dates") or []:
        pl = rd.get("platform")
        key = IGDB_PLATFORM.get(pl.get("name") if isinstance(pl, dict) else None)
        day = unix_to_date(rd.get("date"))
        if key and day and (key not in out or day < out[key]):
            out[key] = day
    return out


def message_key(row: dict[str, Any]) -> str:
    return str(row["game_id"])


def to_connect_message(row: dict[str, Any]) -> dict[str, Any]:
    return {"schema": REFINED_GAME_SCHEMA, "payload": row}
