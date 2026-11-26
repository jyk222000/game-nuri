"""A4 긍정·불만 유형: 게임별 리뷰 키워드를 유형으로 묶어 장르별로 비교한다.

입력: a4_extract_keywords.py가 만든 a4_keywords.tsv (게임별 긍정·부정 키워드와 리뷰 건수)
출력: out/ 아래 차트 PNG 4장, summary.json, unknown_top.csv (사전에 없는 키워드, 보강용)

실행: python analysis/scripts/a4_review_types.py analysis/data/a4_keywords.tsv analysis/results/a4
유형 사전: analysis/dictionaries/review_types.json (코드 analysis/review_types.py)

계산 방식
  - 게임마다 유형별 키워드 건수 합을 구하고, 그 게임의 "분류된 건수" 중 비율(유형 비중)로 바꾼다.
  - 장르·전체 값은 게임 비중의 평균이다 (리뷰가 많은 게임 하나가 결과를 끌지 않게 게임당 1표).
"""

from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "analysis"))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib import font_manager  # noqa: E402
from review_types import aggregate, labels, load_dict  # noqa: E402

SRC, OUT = Path(sys.argv[1]), Path(sys.argv[2])
OUT.mkdir(parents=True, exist_ok=True)
GAMES = ROOT / "analysis" / "game_list" / "games_1000.csv"
MIN_GENRE = 20  # 장르에 게임이 이만큼은 있어야 비교한다
TOP_GENRES = 12
MIN_CLASSIFIED = 10  # 분류된 키워드 건수가 이보다 적은 게임은 비중이 흔들려 뺀다

for f in (
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
):
    if Path(f).exists():
        font_manager.fontManager.addfont(f)
plt.rcParams.update(
    {
        "font.family": "Noto Sans CJK JP",
        "axes.unicode_minus": False,
        "font.size": 11,
        "axes.edgecolor": "#c9c8c3",
        "axes.labelcolor": "#52514e",
        "xtick.color": "#52514e",
        "ytick.color": "#52514e",
    }
)
INK, MUTED, GRID, BG = "#0b0b0b", "#52514e", "#e8e7e3", "#fcfcfb"
NEG_COLORS = ["#eb6834", "#2a78d6", "#7a5bd0", "#009688", "#c9a400", "#a3a29d"]
POS_COLORS = ["#2a78d6", "#009688", "#eb6834", "#c9a400", "#7a5bd0"]


def frame(ax, grid="x"):
    ax.set_facecolor(BG)
    ax.grid(axis=grid, color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)


def save(fig, name):
    fig.tight_layout()
    fig.savefig(OUT / name, dpi=150, facecolor=BG)
    plt.close(fig)


d = load_dict()
neg_labels, pos_labels = labels(d, "negative"), labels(d, "positive")
games = pd.read_csv(GAMES, encoding="utf-8-sig")
games = games.drop_duplicates("game_id").set_index("game_id")

# ---------- 키워드 → 유형 ----------
kw = pd.read_csv(SRC, sep="\t")
rows, unknown_all = [], defaultdict(int)
for (gid, side), g in kw.groupby(["game_id", "side"]):
    pairs = list(zip(g.keyword.astype(str), g.doc_count.astype(int), strict=True))
    counts, unknown = aggregate(pairs, d, side)
    total_all = sum(n for _, n in pairs)
    for w, n in unknown:
        unknown_all[(side, w)] += n
    classified = sum(counts.values())
    rows.append(
        {"game_id": gid, "side": side, "classified": classified, "all": total_all, "counts": counts}
    )
res = pd.DataFrame(rows)


def shares(side: str, keys: list[str]) -> pd.DataFrame:
    """게임 × 유형 비중 (한 게임의 비중 합 = 1)."""
    out = {}
    for r in res[res.side == side].itertuples():
        if r.classified < MIN_CLASSIFIED:
            continue
        out[r.game_id] = {k: r.counts.get(k, 0) / r.classified for k in keys}
    return pd.DataFrame.from_dict(out, orient="index", columns=keys).fillna(0.0)


neg = shares("negative", list(neg_labels))
pos = shares("positive", list(pos_labels))
info = games[["name_ko", "name", "genres", "positive_pct_ko", "review_count_ko"]]
neg = neg.join(info, how="left")
pos = pos.join(info, how="left")

coverage = {}
for side in ("negative", "positive"):
    s = res[res.side == side]
    coverage[side] = {
        "게임 수": int(len(s)),
        "분석에 쓴 게임 수": int((s.classified >= MIN_CLASSIFIED).sum()),
        "사전에 걸린 키워드 건수 비율": round(
            float(s.classified.sum() / max(s["all"].sum(), 1)), 3
        ),
    }


def genre_table(df: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    rows = []
    for _, r in df.iterrows():
        for g in str(r.genres).split("|"):
            if g and g != "nan":
                rows.append({"genre": g, **{k: r[k] for k in keys}})
    t = pd.DataFrame(rows)
    n = t.groupby("genre").size()
    t = t.groupby("genre").mean(numeric_only=True)
    t["n"] = n
    return t[t.n >= MIN_GENRE].sort_values("n", ascending=False).head(TOP_GENRES)


def stacked(ax, t: pd.DataFrame, lab: dict, colors: list[str], title: str):
    keys = list(lab)
    order = t.sort_values(keys[0], ascending=True)
    left = np.zeros(len(order))
    for i, k in enumerate(keys):
        v = order[k].values * 100
        ax.barh(order.index, v, left=left, color=colors[i % len(colors)], label=lab[k], height=0.7)
        for j, (x, w) in enumerate(zip(left, v, strict=True)):
            if w >= 9:
                ax.text(
                    x + w / 2, j, f"{w:.0f}", ha="center", va="center", color="white", fontsize=9
                )
        left += v
    ax.set_yticks(range(len(order)))
    ax.set_yticklabels([f"{g} (n={int(order.n[g])})" for g in order.index])
    ax.set_xlim(0, 100)
    ax.set_xlabel("유형 비중 (%)")
    ax.set_title(title, loc="left", color=INK, fontweight="bold")
    ax.legend(
        ncol=len(keys), loc="upper center", bbox_to_anchor=(0.5, -0.12), frameon=False, fontsize=9
    )
    frame(ax)


# ---------- 차트 1: 전체 ----------
fig, axes = plt.subplots(1, 2, figsize=(12, 4.6))
for ax, df, lab, colors, title in (
    (axes[0], neg, neg_labels, NEG_COLORS, "불만은 무엇 때문인가"),
    (axes[1], pos, pos_labels, POS_COLORS, "만족은 무엇 때문인가"),
):
    m = df[list(lab)].mean().sort_values() * 100
    ax.barh(
        [lab[k] for k in m.index],
        m.values,
        color=[colors[list(lab).index(k)] for k in m.index],
        height=0.65,
    )
    for y, v in enumerate(m.values):
        ax.text(v + 0.5, y, f"{v:.0f}%", va="center", color=INK, fontsize=10)
    ax.set_xlim(0, max(m.values) * 1.2)
    ax.set_xlabel(f"유형 비중 평균 (게임 {len(df)}개)")
    ax.set_title(title, loc="left", color=INK, fontweight="bold")
    frame(ax)
save(fig, "a4_1_overall.png")

# ---------- 차트 2·3: 장르별 ----------
gn, gp = genre_table(neg, list(neg_labels)), genre_table(pos, list(pos_labels))
fig, ax = plt.subplots(figsize=(10, 6.2))
stacked(ax, gn, neg_labels, NEG_COLORS, "장르별 불만 유형")
save(fig, "a4_2_genre_negative.png")
fig, ax = plt.subplots(figsize=(10, 6.2))
stacked(ax, gp, pos_labels, POS_COLORS, "장르별 만족 유형")
save(fig, "a4_3_genre_positive.png")

# ---------- 차트 4: 주된 불만 유형별 유저 긍정률 ----------
neg["dominant"] = neg[list(neg_labels)].idxmax(axis=1)
dom = (
    neg.dropna(subset=["positive_pct_ko"])
    .groupby("dominant")
    .positive_pct_ko.agg(["mean", "count"])
)
dom = dom[dom["count"] >= 5].sort_values("mean")
fig, ax = plt.subplots(figsize=(8.5, 4.6))
ax.barh(
    [f"{neg_labels[k]} (n={int(dom['count'][k])})" for k in dom.index],
    dom["mean"].values,
    color="#2a78d6",
    height=0.65,
)
for y, v in enumerate(dom["mean"].values):
    ax.text(v + 0.5, y, f"{v:.0f}%", va="center", color=INK, fontsize=10)
ax.set_xlim(0, 100)
ax.set_xlabel("한국어 유저 긍정률 평균 (%)")
ax.set_title(
    "주된 불만이 무엇이냐에 따른 평가 (게임 단위)", loc="left", color=INK, fontweight="bold"
)
frame(ax)
save(fig, "a4_4_dominant_vs_rating.png")

# ---------- 요약 ----------
examples = {}
for k in neg_labels:
    top = neg.sort_values(k, ascending=False).head(5)
    examples[neg_labels[k]] = [
        {
            "game": str(r.name_ko if isinstance(r.name_ko, str) else r.name),
            "비중": round(float(r[k]), 2),
        }
        for _, r in top.iterrows()
    ]
summary = {
    "대상": coverage,
    "전체 불만 비중(%)": {neg_labels[k]: round(float(neg[k].mean() * 100), 1) for k in neg_labels},
    "전체 만족 비중(%)": {pos_labels[k]: round(float(pos[k].mean() * 100), 1) for k in pos_labels},
    "주된 불만 유형별 게임 수": {
        neg_labels[k]: int(v) for k, v in neg.dominant.value_counts().items()
    },
    "주된 불만 유형별 긍정률 평균(%)": {
        neg_labels[k]: round(float(r["mean"]), 1) for k, r in dom.iterrows()
    },
    "장르별 불만 1위": {
        g: neg_labels[max(neg_labels, key=lambda k: r[k])] for g, r in gn.iterrows()
    },
    "장르별 만족 1위": {
        g: pos_labels[max(pos_labels, key=lambda k: r[k])] for g, r in gp.iterrows()
    },
    "유형별 대표 게임(불만 비중 상위 5)": examples,
}
(OUT / "summary.json").write_text(
    json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
)

with open(OUT / "unknown_top.csv", "w", encoding="utf-8-sig", newline="") as f:
    w = csv.writer(f)
    w.writerow(["side", "keyword", "doc_count_sum"])
    for (side, word), n in sorted(unknown_all.items(), key=lambda x: -x[1])[:200]:
        w.writerow([side, word, n])
print(json.dumps(summary["대상"], ensure_ascii=False))
print("저장:", OUT)
