from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402

PALETTE = [
    "#5b4bdb",
    "#12a35b",
    "#e8590c",
    "#1c7ed6",
    "#c2255c",
    "#868e96",
    "#f0b429",
    "#2b8a3e",
]  # 웹 --c1~--c8 과 동일
GOOD, BAD, MUTED = "#12a35b", "#d6452f", "#6b7385"
_FONTS = ["Malgun Gothic", "AppleGothic", "NanumGothic", "Noto Sans CJK KR", "Noto Sans KR"]


def setup() -> None:
    """한글 폰트와 공통 스타일. 폰트가 없으면 글자가 깨지므로 경고한다."""
    have = {f.name for f in font_manager.fontManager.ttflist}
    font = next((f for f in _FONTS if f in have), None)
    if font is None:
        print("[warn] 한글 폰트를 찾지 못했어요. NanumGothic 등을 설치하세요.")
    plt.rcParams.update(
        {
            "font.family": font or "sans-serif",
            "axes.unicode_minus": False,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": True,
            "grid.color": "#e4e7ef",
            "grid.linewidth": 0.8,
            "axes.axisbelow": True,
            "axes.titleweight": "bold",
            "axes.titlesize": 13,
            "axes.labelcolor": "#444b5c",
            "figure.facecolor": "white",
            "savefig.facecolor": "white",
            "savefig.dpi": 140,
            "axes.prop_cycle": matplotlib.cycler(color=PALETTE),
        }
    )


def save(fig: plt.Figure, path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path.name
