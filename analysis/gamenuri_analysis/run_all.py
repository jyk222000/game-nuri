"""분석 8개 전체 실행.

python -m gamenuri_analysis.run_all                 # 계산 + 그래프 + B 산출물 (analysis/out)
python -m gamenuri_analysis.run_all --publish       # + 프론트로 복사 (정적 그림, 목 API용 태그)
"""

from __future__ import annotations

import argparse
import json
import shutil
from importlib import import_module
from pathlib import Path

from .export import write_api
from .loader import load_dataset
from .report import OUT_ROOT, Result, fig_dir

MODULES = [
    "a01_discount_pattern",
    "a02_discount_effect",
    "a03_critic_vs_user",
    "a04_complaints",
    "a05_spec_trust",
    "a06_play_pattern",
    "a07_publishers",
    "a08_buzz",
]
REPO = Path(__file__).resolve().parents[2]


def run_all(source: str = "mock", out_root: Path | None = None) -> list[Result]:
    data = load_dataset(source)
    results = []
    for name in MODULES:
        res = import_module(f"{__package__}.{name}").run(data, out_root)
        print(
            f"[ok] {res.key:16s} 그림 {len(res.figures)}개 · 표 {len(res.tables)}개 · 태그 "
            f"{sum(map(len, res.per_game.values()))}개"
        )
        results.append(res)
    for p in write_api(results, source, out_root):
        print(f"[ok] B 산출물 {p.relative_to(out_root or OUT_ROOT)}")
    return results


def publish(results: list[Result], out_root: Path | None = None) -> None:
    """프론트가 읽을 위치로 복사한다.

    A: public/analysis-data/<분석>/ (PNG + summary.json)
    B(목 API용): src/api/mock/generated/ 의 game_insights.json, spec_trust.json
    """
    root = out_root or OUT_ROOT
    fe = REPO / "frontend"
    pub = fe / "public" / "analysis-data"
    if pub.exists():
        shutil.rmtree(pub)
    index = []
    for r in results:
        dst = pub / r.key
        dst.mkdir(parents=True, exist_ok=True)
        for f in fig_dir(r.key, root).iterdir():
            shutil.copy2(f, dst / f.name)
        index.append({"key": r.key, "title": r.title})
    (pub / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    gen = fe / "src" / "api" / "mock" / "generated"
    gen.mkdir(parents=True, exist_ok=True)
    for name in ("game_insights.json", "spec_trust.json"):
        shutil.copy2(root / "api" / name, gen / name)
    print(f"[ok] 프론트로 복사: {pub.relative_to(REPO)}, {gen.relative_to(REPO)}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="mock", choices=["mock", "db"])
    ap.add_argument("--publish", action="store_true")
    a = ap.parse_args()
    results = run_all(a.source)
    if a.publish:
        publish(results)


if __name__ == "__main__":
    main()
