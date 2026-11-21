from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

OUT_ROOT = Path(__file__).resolve().parents[1] / "out"  # analysis/out (Git 제외)


@dataclass
class Result:
    """분석 하나의 결과. figures/tables/takeaways 는 프론트 /analysis 화면(A),
    per_game 은 게임별 태그(B), api 는 Backend 가 쓰는 규칙(B)."""

    key: str
    title: str
    source: str
    takeaways: list[str] = field(default_factory=list)
    figures: list[dict[str, Any]] = field(default_factory=list)
    tables: list[dict[str, Any]] = field(default_factory=list)
    per_game: dict[int, list[dict[str, str]]] = field(default_factory=dict)
    api: dict[str, Any] = field(default_factory=dict)
    dfs: dict[str, pd.DataFrame] = field(default_factory=dict)  # 노트북에서 들여다볼 중간 결과
    items: dict[str, dict[int, dict[str, Any]]] = field(
        default_factory=dict
    )  # B: 게임별 서비스 데이터 {파일이름: {game_id: {...}}}

    def fig(
        self, file: str, title: str, caption: str, charts: list[dict[str, Any]] | None = None
    ) -> None:
        """그림을 등록한다.

        file = 파이썬이 그린 PNG, charts = 같은 값으로 웹 화면이 직접 그릴 차트 명세(charts.py).
        """
        self.figures.append(
            {"file": file, "title": title, "caption": caption, "charts": charts or []}
        )

    def attach_to(self, file: str, *charts: dict[str, Any]) -> None:
        """이미 등록한 그림(file)에 웹용 차트 명세를 붙인다.

        그림 하나에 패널이 여러 개일 수 있다.
        """
        for f in self.figures:
            if f["file"] == file:
                f["charts"] = list(charts)
                return
        raise KeyError(file)

    def table(self, title: str, df: pd.DataFrame, note: str = "") -> None:
        self.tables.append(
            {
                "title": title,
                "note": note,
                "columns": [str(c) for c in df.columns],
                "rows": json.loads(df.to_json(orient="values", force_ascii=False)),
            }
        )

    def tag(self, game_id: int, code: str, label: str, tone: str, detail: str) -> None:
        self.per_game.setdefault(int(game_id), []).append(
            {"code": code, "label": label, "tone": tone, "detail": detail, "analysis": self.key}
        )

    def summary(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "title": self.title,
            "data_source": self.source,
            "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "takeaways": self.takeaways,
            "figures": self.figures,
            "tables": self.tables,
        }


def fig_dir(key: str, out_root: Path | None = None) -> Path:
    return (out_root or OUT_ROOT) / "figures" / key


def write_summary(res: Result, out_root: Path | None = None) -> Path:
    p = fig_dir(res.key, out_root) / "summary.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(res.summary(), ensure_ascii=False, indent=1), encoding="utf-8")
    return p
