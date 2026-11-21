"""B: Backend 가 API 로 내려 줄 JSON 산출물 (게임별 분석 태그, 구매 타이밍 규칙)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .report import OUT_ROOT, Result

TONE_ORDER = {"warn": 0, "good": 1, "info": 2}
MAX_TAGS = 5


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def game_insights(results: list[Result], source: str) -> dict[str, Any]:
    """게임 상세 응답의 insights 필드. {game_id: [{code,label,tone,detail,analysis}]}"""
    merged: dict[int, list[dict[str, str]]] = {}
    for r in results:
        for gid, tags in r.per_game.items():
            merged.setdefault(gid, []).extend(tags)
    items = {
        str(g): sorted(t, key=lambda x: TONE_ORDER.get(x["tone"], 9))[:MAX_TAGS]
        for g, t in sorted(merged.items())
    }
    return {"generated_at": _now(), "data_source": source, "items": items}


def timing_rules(results: list[Result], source: str) -> dict[str, Any]:
    """구매 타이밍 규칙. Backend 가 현재 할인율·게임 나이·월과 비교해 '지금 살지'를 판단한다."""
    by = {r.key: r for r in results}
    return {
        "version": 1,
        "generated_at": _now(),
        "data_source": source,
        **by["discount-pattern"].api,
        "spec_trust": by["spec-trust"].api,
    }


def spec_trust(results: list[Result], source: str) -> dict[str, Any]:
    """게임 상세 사양표 옆에 보여 줄 신뢰도. GET /api/games/{id}/requirements 응답의 trust 필드."""
    r = next(x for x in results if x.key == "spec-trust")
    return {
        "generated_at": _now(),
        "data_source": source,
        "rule": r.api,
        "items": {str(g): v for g, v in sorted(r.items["spec_trust"].items())},
    }


def write_api(results: list[Result], source: str, out_root: Path | None = None) -> list[Path]:
    d = (out_root or OUT_ROOT) / "api"
    d.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, obj in [
        ("game_insights.json", game_insights(results, source)),
        ("timing_rules.json", timing_rules(results, source)),
        ("spec_trust.json", spec_trust(results, source)),
    ]:
        p = d / name
        p.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
        paths.append(p)
    return paths
