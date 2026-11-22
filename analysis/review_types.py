"""A4 긍정·불만 유형: ES 리뷰 키워드 → 유형별 건수.

    from review_types import load_dict, aggregate
    d = load_dict()
    counts, unknown = aggregate([("최적화", 120), ("프레임", 40), ("lag", 9)], d, "negative")
    # counts = {"optimization": 169}, unknown = []

규칙
  - 한국어: 사전 단어로 시작하면 그 유형 (nori 어간이 "비싸"·"비쌉" 처럼 갈라져도 잡도록)
  - 영어: 소문자로 바꿔 단어가 정확히 같을 때만
  - 어느 유형에도 없으면 unknown 으로 돌려준다 → 사전을 보강할 때 본다
  - 여러 유형에 걸리면 사전에 먼저 적힌 유형 하나만 (중복 집계 안 함)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DICT_PATH = Path(__file__).resolve().parent / "dictionaries" / "review_types.json"


def load_dict(path: Path | str = DICT_PATH) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def classify(keyword: str, d: dict[str, Any], side: str) -> str | None:
    """키워드 하나 → 유형 키 (side 는 "negative" 또는 "positive"). 없으면 None."""
    word = keyword.strip()
    if not word:
        return None
    lower = word.lower()
    for cat, spec in d[side].items():
        if lower in spec.get("en", []):
            return cat
        if any(word.startswith(stem) for stem in spec.get("ko", [])):
            return cat
    return None


def aggregate(
    keyword_counts: list[tuple[str, int]], d: dict[str, Any], side: str
) -> tuple[dict[str, int], list[tuple[str, int]]]:
    """[(키워드, 건수)] → ({유형: 건수 합}, [분류 못 한 (키워드, 건수)])."""
    counts: dict[str, int] = {}
    unknown: list[tuple[str, int]] = []
    for word, n in keyword_counts:
        cat = classify(word, d, side)
        if cat is None:
            unknown.append((word, n))
        else:
            counts[cat] = counts.get(cat, 0) + int(n)
    return counts, unknown


def labels(d: dict[str, Any], side: str) -> dict[str, str]:
    return {k: v["label"] for k, v in d[side].items()}
