"""A3 평론 vs 유저 평가 괴리 + 유저 긍정률 예측.

입력: MariaDB Replica에서 뽑은 a3_games.tsv (games + game_review_stats + 장르 + 동접)
출력: out/ 아래 차트 PNG 6장, summary.json, gap_top.csv

실행: python analysis/scripts/a3_critic_vs_user.py analysis/data/a3_games.tsv analysis/results/a3
데이터 추출: analysis/scripts/a3_extract.sql (2026-11-25 mariadb-re, 게임 916개)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib import font_manager
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import KFold, cross_val_predict

SRC, OUT = Path(sys.argv[1]), Path(sys.argv[2])
OUT.mkdir(parents=True, exist_ok=True)

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
BLUE, ORANGE, GRAY = "#2a78d6", "#eb6834", "#a3a29d"
INK, MUTED, GRID, BG = "#0b0b0b", "#52514e", "#e8e7e3", "#fcfcfb"
MIN_CRITICS = 3  # 평론 3개 이상 모인 게임만 (평론 1~2개는 점수가 흔들린다)
MIN_GENRE = 30
SEED = 42


def frame(ax, grid="both"):
    ax.set_facecolor(BG)
    ax.grid(axis=grid, color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)


def save(fig, name):
    fig.tight_layout()
    fig.savefig(OUT / name, dpi=150, facecolor=BG)
    plt.close(fig)


d = pd.read_csv(SRC, sep="\t", na_values=["NULL"])
d["year"] = pd.to_datetime(d.release_date, errors="coerce").dt.year
a = d[(d.aggregated_rating > 0) & (d.aggregated_rating_count >= MIN_CRITICS)].copy()
a["gap"] = a.positive_pct_ko - a.aggregated_rating  # + 면 유저가 더 후함
n = len(a)
rho = a.aggregated_rating.corr(a.positive_pct_ko, method="spearman")
summary: dict = {
    "games_total": len(d),
    "games_used": n,
    "min_critics": MIN_CRITICS,
    "spearman_critic_user": round(rho, 3),
}

# 1) 산점도 -----------------------------------------------------------------
fig, ax = plt.subplots(figsize=(8.5, 6.2), facecolor=BG)
frame(ax)
ax.plot([0, 100], [0, 100], color=MUTED, lw=1, ls="--")
ax.text(98, 99, "평론 = 유저", color=MUTED, ha="right", va="bottom", fontsize=9)
ax.scatter(
    a.aggregated_rating, a.positive_pct_ko, s=22, color=BLUE, alpha=0.5, edgecolor=BG, lw=0.6
)
# 이름표 위치 (유저가 더 후한 3개, 평론이 더 후한 3개: 점이 붙어 있어 겹치지 않게)
LABEL_POS = [(6, -3, "left")] * 3 + [(6, -12, "left"), (6, 5, "left"), (-6, 5, "right")]
top_hi = a.nlargest(3, "gap")
top_lo = a.nsmallest(3, "gap")
for j, (_, r) in enumerate(pd.concat([top_hi, top_lo]).iterrows()):
    ax.scatter(
        r.aggregated_rating,
        r.positive_pct_ko,
        s=40,
        color=BLUE if r.gap > 0 else ORANGE,
        edgecolor=INK,
        lw=0.8,
        zorder=3,
    )
    dx, dy, ha = LABEL_POS[j]
    ax.annotate(
        r["name"],
        (r.aggregated_rating, r.positive_pct_ko),
        xytext=(dx, dy),
        textcoords="offset points",
        fontsize=8.5,
        color=INK,
        ha=ha,
    )
ax.set_xlim(40, 100)
ax.set_ylim(20, 101)
ax.set_xlabel("평론 점수 (IGDB aggregated_rating)")
ax.set_ylabel("Steam 한국어 리뷰 긍정 %")
ax.set_title(
    f"평론 점수와 한국 유저 평가는 약하게만 같이 움직인다 (게임 {n}개, 순위상관 {rho:.2f})",
    loc="left",
    fontsize=12.5,
    color=INK,
)
save(fig, "a3_1_scatter.png")

# 2) 장르별 괴리 -------------------------------------------------------------
g = a.assign(genre=a.genres.str.split("|")).explode("genre")
t = (
    g.groupby("genre")
    .agg(n=("gap", "size"), gap=("gap", "mean"))
    .query("n >= @MIN_GENRE")
    .sort_values("gap")
)
fig, ax = plt.subplots(figsize=(8.5, 6.2), facecolor=BG)
frame(ax, "x")
ax.barh(
    t.index,
    t.gap,
    color=[BLUE if v >= 0 else ORANGE for v in t.gap],
    height=0.66,
    edgecolor=BG,
    lw=2,
)
ax.axvline(0, color=MUTED, lw=1)
for i, (v, k) in enumerate(zip(t.gap, t.n, strict=True)):
    ax.text(
        v + (0.3 if v >= 0 else -0.3),
        i,
        f"{v:+.1f} ({k})",
        va="center",
        ha="left" if v >= 0 else "right",
        fontsize=8.5,
        color=MUTED,
    )
lim = max(abs(t.gap.min()), abs(t.gap.max())) + 4
ax.set_xlim(-lim, lim)
ax.set_xlabel("유저 긍정 % − 평론 점수 (평균, 괄호는 게임 수)")
ax.set_title("장르마다 평론과 유저가 갈린다", loc="left", fontsize=12.5, color=INK)
ax.text(
    lim,
    len(t) - 0.3,
    "파랑 = 유저가 더 후함 · 주황 = 평론이 더 후함",
    ha="right",
    fontsize=8.5,
    color=MUTED,
)
save(fig, "a3_2_genre_gap.png")
summary["genre_gap"] = {k: {"n": int(r.n), "gap": round(r.gap, 1)} for k, r in t.iterrows()}

# 3) 출시 시기별 -------------------------------------------------------------
bins = [1980, 2010, 2015, 2020, 2023, 2030]
labels = ["~2010", "2011~15", "2016~20", "2021~23", "2024~"]
y = a.groupby(pd.cut(a.year, bins, labels=labels), observed=False).agg(
    n=("gap", "size"), critic=("aggregated_rating", "mean"), user=("positive_pct_ko", "mean")
)
fig, ax = plt.subplots(figsize=(8.5, 5.4), facecolor=BG)
frame(ax, "y")
x = np.arange(len(y))
ax.plot(x, y.critic, color=ORANGE, lw=2, marker="o", ms=8, mec=BG, mew=2, label="평론 점수")
ax.plot(x, y.user, color=BLUE, lw=2, marker="o", ms=8, mec=BG, mew=2, label="한국 유저 긍정 %")
for i, r in enumerate(y.itertuples()):
    ax.text(
        i,
        max(r.critic, r.user) + 1.2,
        f"{r.user - r.critic:+.1f}",
        ha="center",
        fontsize=9,
        color=INK,
    )
ax.set_xticks(x, [f"{lab}\n({k}개)" for lab, k in zip(labels, y.n, strict=True)])
ax.set_ylim(65, 95)
ax.legend(frameon=False, loc="lower left")
ax.set_title(
    "2021년 이후 게임은 평론이 유저보다 후하다 (숫자 = 유저 − 평론)",
    loc="left",
    fontsize=12.5,
    color=INK,
)
save(fig, "a3_3_by_year.png")
summary["by_year"] = {
    lab: {"n": int(r.n), "critic": round(r.critic, 1), "user": round(r.user, 1)}
    for lab, r in zip(labels, y.itertuples(), strict=True)
}

# 4) 한국 유저 vs 전체 유저 ---------------------------------------------------
d["kgap"] = d.positive_pct_ko - d.positive_pct_all
k = d.groupby("korean_supported").kgap.agg(["size", "mean", "median"])
fig, ax = plt.subplots(figsize=(8.5, 4.6), facecolor=BG)
frame(ax, "x")
names = {0: "한국어 미지원", 1: "한국어 지원"}
rows = [(names[i], r["mean"], int(r["size"])) for i, r in k.iterrows()]
ax.barh([r[0] for r in rows], [r[1] for r in rows], color=ORANGE, height=0.5, edgecolor=BG, lw=2)
for i, (_, v, cnt) in enumerate(rows):
    ax.text(v - 0.15, i, f"{v:+.1f}%p ({cnt}개)", va="center", ha="right", fontsize=10, color=INK)
ax.axvline(0, color=MUTED, lw=1)
ax.set_xlim(min(r[1] for r in rows) - 3, 1)
ax.set_xlabel("한국어 리뷰 긍정 % − 전체 언어 리뷰 긍정 % (평균)")
ax.set_title(
    f"한국 유저는 전 세계 평균보다 박하다 (전체 {len(d)}개 평균 {d.kgap.mean():+.1f}%p)",
    loc="left",
    fontsize=12.5,
    color=INK,
)
save(fig, "a3_4_korea_vs_global.png")
summary["korea_vs_global"] = {
    "mean_gap": round(d.kgap.mean(), 2),
    "harsher_share": round((d.kgap < 0).mean(), 3),
    "by_korean_supported": {
        names[i]: {"n": int(r["size"]), "mean": round(r["mean"], 2)} for i, r in k.iterrows()
    },
}

# 5) 예측 모델: 평론·출시연도·장르·온라인 등으로 한국 유저 긍정률 예측 -----------
top_genres = g.genre.value_counts().loc[lambda s: s >= MIN_GENRE].index.tolist()
X = pd.DataFrame(
    {
        "평론 점수": a.aggregated_rating,
        "평론 수": a.aggregated_rating_count,
        "출시 연도": a.year.fillna(a.year.median()),
        "온라인": a.is_online,
        "한국어 지원": a.korean_supported,
        "연령 등급": a.age_rating,
        "최대 동접(log)": np.log10(a.peak_players.clip(lower=1)),
        "한국어 리뷰 수(log)": np.log10(a.review_count_ko.clip(lower=1)),
    },
    index=a.index,
)
for gname in top_genres:
    X[f"장르:{gname}"] = a.genres.str.split("|").apply(lambda s, gn=gname: int(gn in s))
yv = a.positive_pct_ko.values
cv = KFold(5, shuffle=True, random_state=SEED)
models = {
    "평균값 (기준)": None,
    "평론 점수만 (선형)": ("one", LinearRegression()),
    "전체 요소 (선형)": ("all", LinearRegression()),
    "전체 요소 (부스팅)": (
        "all",
        GradientBoostingRegressor(
            random_state=SEED, max_depth=3, n_estimators=300, learning_rate=0.03, subsample=0.8
        ),
    ),
}
res = {}
preds = {}
for name, spec in models.items():
    if spec is None:
        p = np.full_like(yv, yv.mean(), dtype=float)
    else:
        cols, m = spec
        Xm = X[["평론 점수"]] if cols == "one" else X
        p = cross_val_predict(m, Xm, yv, cv=cv)
    preds[name] = p
    res[name] = {
        "mae": round(float(np.mean(np.abs(yv - p))), 2),
        "r2": round(float(1 - np.sum((yv - p) ** 2) / np.sum((yv - yv.mean()) ** 2)), 3),
    }
summary["model"] = res

fig, ax = plt.subplots(figsize=(8.5, 4.6), facecolor=BG)
frame(ax, "x")
names_m = list(res)
maes = [res[m]["mae"] for m in names_m]
ax.barh(
    names_m[::-1], maes[::-1], color=[GRAY, BLUE, BLUE, BLUE][::-1], height=0.55, edgecolor=BG, lw=2
)
for i, m in enumerate(names_m[::-1]):
    ax.text(
        res[m]["mae"] + 0.08,
        i,
        f"평균 {res[m]['mae']:.1f}%p 틀림 · R² {res[m]['r2']:.2f}",
        va="center",
        fontsize=9.5,
        color=INK,
    )
ax.set_xlim(0, max(maes) * 1.55)
ax.set_xlabel("평균 절대 오차 (%p, 5겹 교차검증) — 짧을수록 정확")
ax.set_title("평론 점수만으로는 유저 평가를 거의 못 맞힌다", loc="left", fontsize=12.5, color=INK)
save(fig, "a3_5_model_error.png")

gb = models["전체 요소 (부스팅)"][1].fit(X, yv)
pi = permutation_importance(
    gb, X, yv, n_repeats=20, random_state=SEED, scoring="neg_mean_absolute_error"
)
imp = pd.Series(pi.importances_mean, index=X.columns).sort_values(ascending=False).head(10)
summary["importance_top10"] = {k_: round(float(v), 3) for k_, v in imp.items()}
fig, ax = plt.subplots(figsize=(8.5, 5.2), facecolor=BG)
frame(ax, "x")
imp_r = imp[::-1]
ax.barh(imp_r.index, imp_r.values, color=BLUE, height=0.6, edgecolor=BG, lw=2)
for i, v in enumerate(imp_r.values):
    ax.text(v + 0.01, i, f"{v:.2f}", va="center", fontsize=9, color=MUTED)
ax.set_xlabel("이 요소를 섞으면 오차가 늘어나는 양 (%p) — 클수록 중요")
ax.set_title(
    "유저 긍정률을 가르는 요소 (부스팅 모델, 상위 10개)", loc="left", fontsize=12.5, color=INK
)
save(fig, "a3_6_importance.png")

# 숨은 명작 / 과대평가 후보: 모델 예측보다 실제가 크게 높거나 낮은 게임
a["pred"] = preds["전체 요소 (부스팅)"]
a["resid"] = a.positive_pct_ko - a.pred
cols = [
    "game_id",
    "name",
    "year",
    "aggregated_rating",
    "positive_pct_ko",
    "gap",
    "pred",
    "resid",
    "genres",
]
top = pd.concat(
    [
        a.nlargest(10, "gap").assign(kind="유저가 더 후함 (숨은 명작 후보)"),
        a.nsmallest(10, "gap").assign(kind="평론이 더 후함 (과대평가 후보)"),
    ]
)
top[["kind", *cols]].round(1).to_csv(OUT / "gap_top.csv", index=False, encoding="utf-8-sig")
summary["hidden_gems"] = a.nlargest(5, "gap")["name"].tolist()
summary["overrated"] = a.nsmallest(5, "gap")["name"].tolist()

(OUT / "summary.json").write_text(
    json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
)
print(json.dumps(summary, ensure_ascii=False, indent=2))
