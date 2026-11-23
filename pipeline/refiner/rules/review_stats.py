"""raw.steam(review_summary = GetItems) → refined.review_stats. 순수 함수.

payload = GetItems 응답 store_items[] 원소 하나
(docs/contracts/messages/raw.steam.review_summary.json).
  *_ko  ← reviews.summary_language_specific (한국어 리뷰, 스토어 표시값)
  *_all ← reviews.summary_filtered (스토어 기본 표시, 전체 언어)
항목이 없으면 null. 리뷰가 하나도 없는 게임(reviews 없음)은 행을 만들지 않는다.
AI 요약(review_summaries)과 다른 테이블이라 서로 덮어쓰지 않는다.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

REFINED_REVIEW_STATS_SCHEMA: dict[str, Any] = {
    "type": "struct",
    "name": "refined_review_stats",
    "fields": [
        {"field": "game_id", "type": "int64", "optional": False},
        {"field": "review_count_ko", "type": "int32", "optional": True},
        {"field": "positive_pct_ko", "type": "int16", "optional": True},
        {"field": "review_score_ko", "type": "int16", "optional": True},
        {"field": "review_label_ko", "type": "string", "optional": True},
        {"field": "review_count_all", "type": "int32", "optional": True},
        {"field": "positive_pct_all", "type": "int16", "optional": True},
        {"field": "review_label_all", "type": "string", "optional": True},
        {"field": "updated_at", "type": "string", "optional": False},
    ],
}


def _int(v: Any) -> int | None:
    if v is None or isinstance(v, bool):
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _label(v: Any) -> str | None:
    return v.strip() if isinstance(v, str) and v.strip() else None


def _appid(payload: dict[str, Any], envelope: dict[str, Any]) -> int | None:
    params = (envelope.get("request") or {}).get("params") or {}
    for v in (payload.get("appid"), payload.get("id"), params.get("appid")):
        if _int(v) is not None:
            return _int(v)
    return None


def refine_review_stats(
    envelope: dict[str, Any], resolve_game_id: Callable[[int], int | None]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    payload = envelope.get("payload") or {}
    collected_at = envelope.get("collected_at")
    appid = _appid(payload, envelope)
    game_id = resolve_game_id(appid) if appid is not None else None
    if game_id is None:
        return [], [
            {
                "reason": "Steam appid → IGDB ID 매칭 실패 (리뷰 요약)",
                "source": "steam",
                "key": appid,
                "collected_at": collected_at,
            }
        ]
    reviews = payload.get("reviews")
    if not isinstance(reviews, dict) or not reviews:
        return [], []
    ko = reviews.get("summary_language_specific") or {}
    al = reviews.get("summary_filtered") or {}
    return [
        {
            "game_id": int(game_id),
            "review_count_ko": _int(ko.get("review_count")),
            "positive_pct_ko": _int(ko.get("percent_positive")),
            "review_score_ko": _int(ko.get("review_score")),
            "review_label_ko": _label(ko.get("review_score_label")),
            "review_count_all": _int(al.get("review_count")),
            "positive_pct_all": _int(al.get("percent_positive")),
            "review_label_all": _label(al.get("review_score_label")),
            "updated_at": collected_at,
        }
    ], []


def message_key(row: dict[str, Any]) -> str:
    return str(row["game_id"])


def to_connect_message(row: dict[str, Any]) -> dict[str, Any]:
    return {"schema": REFINED_REVIEW_STATS_SCHEMA, "payload": row}
