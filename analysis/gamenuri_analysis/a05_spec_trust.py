"""⑤ 사양표는 믿을 만한가 — 리뷰 키워드로 본 사양표 신뢰도.

게임 상세의 사양표 옆에 "이 사양표를 믿어도 되나"를 알려 주는 지표다. 사양을 등급으로 매기지 않는다.
지표 = 최근 N개월 부정 리뷰 중 성능 문제(최적화·프레임·끊김·렉·발열·튕김) 언급 비율.
한계: 리뷰어가 사양을 충족했는지는 모른다. 그래서 '참고 지표'로만 표시한다.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from matplotlib import pyplot as plt

from . import charts as ch
from . import style
from .dataset import Dataset
from .report import Result, fig_dir, write_summary

KEY = "spec-trust"
WINDOW = 6  # 최근 N개월
MIN_REVIEWS = 50  # 최근 창의 분류된 부정 리뷰가 이보다 적으면 판단 보류
MIN_AGE = 9  # 출시 후 이 개월 이상이어야 '초기 → 최근' 비교
BAD_PCT, CAUTION_PCT, BAD_FLOOR, CAUTION_FLOOR = (
    85,
    60,
    25.0,
    15.0,
)  # 백분위 기준 + 최소 절대값(임시, 실데이터로 재조정)
LABEL = {"good": "신뢰할 만해요", "caution": "주의", "bad": "믿기 어려워요", "hold": "판단 보류"}
COLOR = {"good": 2, "caution": 7, "bad": 5, "hold": 6}  # 웹 --c번호 (= style.PALETTE[번호-1])


def _num(v: Any, d: int = 1) -> float | None:
    f = float(v)
    return None if math.isnan(f) or math.isinf(f) else round(f, d)


def _share(c: pd.DataFrame) -> tuple[float, int]:
    tot = int(c["count"].sum())
    return (
        c.loc[c.category == "optimization", "count"].sum() / tot * 100 if tot else float("nan")
    ), tot


def _metrics(d: Dataset) -> pd.DataFrame:
    rows = []
    for gid, c in d.complaints.groupby("game_id"):
        last = int(c.month.max())
        rec, n_rec = _share(c[c.month > last - WINDOW])
        launch, _ = _share(c[c.month <= 2]) if last >= MIN_AGE else (float("nan"), 0)
        rows.append((gid, last, rec, n_rec, launch))
    m = pd.DataFrame(
        rows, columns=["game_id", "age_months", "recent_share", "n_recent", "launch_share"]
    )
    ok = m.n_recent >= MIN_REVIEWS
    p_bad = max(float(np.percentile(m.recent_share[ok], BAD_PCT)), BAD_FLOOR)
    p_cau = max(float(np.percentile(m.recent_share[ok], CAUTION_PCT)), CAUTION_FLOOR)
    m["verdict"] = np.select(
        [~ok, m.recent_share >= p_bad, m.recent_share >= p_cau], ["hold", "bad", "caution"], "good"
    )
    m["top_pct"] = m.recent_share.rank(ascending=False, method="min").div(ok.sum()).mul(100).round()
    m.attrs["thresholds"] = {"bad": round(p_bad, 1), "caution": round(p_cau, 1)}
    return m


def _reason(r: Any) -> str:
    if r.verdict == "hold":
        return (
            f"리뷰가 아직 적어서(최근 {WINDOW}개월 분류된 부정 리뷰 {int(r.n_recent)}건) "
            "판단을 보류해요."
        )
    base = (
        f"최근 {WINDOW}개월 부정 리뷰의 {r.recent_share:.0f}%가 성능 문제"
        f"(최적화·프레임·끊김 등)를 말해요 (전체 게임 중 상위 {r.top_pct:.0f}%)."
    )
    if pd.notna(r.launch_share) and r.launch_share - r.recent_share >= 5:
        base += (
            f" 출시 초기 {r.launch_share:.0f}% → 최근 {r.recent_share:.0f}%로 나아지는 중이에요."
        )
    return base


def run(d: Dataset, out_root: Path | None = None) -> Result:
    style.setup()
    out = fig_dir(KEY, out_root)
    res = Result(KEY, "사양표 신뢰도", d.source)
    g = d.games.set_index("game_id")
    m = _metrics(d)
    th = m.attrs["thresholds"]
    m["name"] = m.game_id.map(g.name)
    res.dfs["trust"] = m

    kw = d.perf_keywords[d.perf_keywords.game_id.isin(m.game_id)]
    kwtot = kw.groupby("game_id")["count"].sum()
    items: dict[int, dict[str, Any]] = {}
    for r in m.itertuples():
        top = kw[kw.game_id == r.game_id].nlargest(3, "count")
        denom = kwtot.get(r.game_id, 0) or 1
        items[int(r.game_id)] = {
            "verdict": r.verdict,
            "label": LABEL[r.verdict],
            "recent_share": _num(r.recent_share),
            "launch_share": _num(r.launch_share),
            "top_pct": _num(r.top_pct, 0),
            "n_reviews": int(r.n_recent),
            "window_months": WINDOW,
            "keywords": [
                {"keyword": k.keyword, "share": round(k.count / denom * 100)}
                for k in top.itertuples()
            ]
            if r.verdict != "hold"
            else [],
            "reason": _reason(r),
        }
    res.items["spec_trust"] = items

    # 그림 1: 분포 + 기준선
    ok = m[m.verdict != "hold"]
    edges = np.arange(0, 60, 5)
    cnt, _ = np.histogram(ok.recent_share.clip(upper=59.9), bins=edges)
    fig, ax = plt.subplots(figsize=(10, 4.4))
    ax.bar(edges[:-1] + 2.5, cnt, width=4.4, color=style.PALETTE[0])
    ax.axvline(th["caution"], color=style.PALETTE[6], ls="--", lw=2)
    ax.axvline(th["bad"], color=style.PALETTE[4], ls="--", lw=2)
    ax.text(
        th["caution"] + 0.5,
        cnt.max() * 0.95,
        f"주의 {th['caution']:.0f}%~",
        color="#b08900",
        fontsize=9,
    )
    ax.text(
        th["bad"] + 0.5,
        cnt.max() * 0.80,
        f"믿기 어려움 {th['bad']:.0f}%~",
        color=style.PALETTE[4],
        fontsize=9,
    )
    ax.set(
        xlabel=f"최근 {WINDOW}개월 부정 리뷰 중 성능 문제 언급 비율(%)",
        ylabel="게임 수",
        title="게임 대부분은 낮고, 일부만 유독 높다",
    )
    res.fig(
        style.save(fig, out / "dist.png"),
        "성능 문제 언급 비율 분포",
        f"게임 {len(ok)}개의 분포예요. 상위 {100 - BAD_PCT}%(또는 {BAD_FLOOR:.0f}% 이상)면 '믿기 "
        f"어려워요', 상위 {100 - CAUTION_PCT}%(또는 {CAUTION_FLOOR:.0f}% 이상)면 '주의'로 "
        "표시해요. 기준은 임시이고 실데이터로 조정해요.",
    )
    edge_lab = [f"{int(a)}~{int(a) + 5}" for a in edges[:-1]]
    res.attach_to(
        "dist.png",
        ch.bars(
            f"최근 {WINDOW}개월 성능 문제 언급 비율 분포 (게임 수)",
            [{"label": lb, "value": int(v)} for lb, v in zip(edge_lab, cnt, strict=True)],
            orient="v",
            xlabel="부정 리뷰 중 성능 문제 언급 비율(%)",
            marks=[
                {"pos": th["caution"] / 5, "label": f"주의 {th['caution']:.0f}%~"},
                {"pos": th["bad"] / 5, "label": f"믿기 어려움 {th['bad']:.0f}%~"},
            ],
        ),
    )

    # 그림 2: 출시 초기 vs 최근
    both = m[m.launch_share.notna() & (m.verdict != "hold")]
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot([0, 60], [0, 60], color=style.MUTED, ls="--", lw=1)
    for v in ["good", "caution", "bad"]:
        s = both[both.verdict == v]
        ax.scatter(
            s.launch_share,
            s.recent_share,
            s=55,
            alpha=0.85,
            color=style.PALETTE[COLOR[v] - 1],
            edgecolor="white",
            label=LABEL[v],
        )
    lab = pd.concat(
        [
            both[both.verdict == "bad"],
            both.assign(d=both.launch_share - both.recent_share).nlargest(3, "d"),
        ]
    ).drop_duplicates("game_id")
    labelled = set(lab.game_id)
    for r in lab.itertuples():
        ax.annotate(
            r.name,
            (r.launch_share, r.recent_share),
            xytext=(6, 5),
            textcoords="offset points",
            fontsize=8,
        )
    ax.text(44, 29, "대각선 아래 = 나아짐", color=style.GOOD, fontsize=9, rotation=34)
    ax.set(
        xlabel="출시 초기(0~2개월) 성능 문제 언급 비율(%)",
        ylabel=f"최근 {WINDOW}개월(%)",
        xlim=(0, 60),
        ylim=(0, 60),
        title="패치로 나아진 게임은 대각선 아래에 있다",
    )
    ax.legend(frameon=False)
    res.fig(
        style.save(fig, out / "change.png"),
        "출시 초기 → 최근 변화",
        "대각선 아래 = 출시 초기보다 성능 불만이 줄었어요. 초기엔 문제였지만 지금은 괜찮은 게임을 "
        "가려낼 수 있어요.",
    )
    res.attach_to(
        "change.png",
        ch.scatter(
            "패치로 나아진 게임은 대각선 아래에 있다",
            [
                {
                    "x": r.launch_share,
                    "y": r.recent_share,
                    "group": LABEL[r.verdict],
                    "label": r.name if r.game_id in labelled else None,
                }
                for r in both.itertuples()
            ],
            groups=[{"name": LABEL[v], "color": COLOR[v]} for v in ["good", "caution", "bad"]],
            xlabel="출시 초기(0~2개월) 성능 문제 언급 비율",
            ylabel=f"최근 {WINDOW}개월",
            xunit="%",
            yunit="%",
            xlim=(0, 60),
            ylim=(0, 60),
            diagonal=True,
        ),
    )

    # 그림 3: 출시 후 추이 + Steam Deck
    c = d.complaints
    by_m = c.pivot_table(index="month", columns="category", values="count", aggfunc="sum")
    trend = (by_m["optimization"] / by_m.sum(axis=1) * 100).loc[:18]
    dv = d.deck_reviews.groupby("device")[["n_opt", "n_reviews"]].sum()
    rate = (dv.n_opt / dv.n_reviews * 100).round(1)
    drop = (1 - trend.iloc[-6:].mean() / trend.iloc[:3].mean()) * 100
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(10, 4.2), gridspec_kw={"width_ratios": [1.6, 1]})
    a1.plot(trend.index, trend.values, color=style.PALETTE[0], lw=2.4)
    a1.set_ylim(0, trend.max() * 1.15)
    a1.set(
        title="출시 후 성능 문제 언급 비율(전체 평균)",
        xlabel="출시 후 개월",
        ylabel="부정 리뷰 중 비중(%)",
    )
    a2.bar(
        ["데스크톱", "Steam Deck"],
        [rate.get("desktop", 0), rate.get("deck", 0)],
        color=[style.PALETTE[5], style.PALETTE[2]],
    )
    for i, v in enumerate([rate.get("desktop", 0), rate.get("deck", 0)]):
        a2.text(i, v + 0.8, f"{v}%", ha="center")
    a2.set(title="기기별 성능 문제 리뷰", ylabel="리뷰 중 언급(%)")
    res.fig(
        style.save(fig, out / "trend_deck.png"),
        "출시 후 추이 · Steam Deck 비교",
        "시간이 지나며 성능 문제가 줄어드는지, 휴대용(Steam Deck)에서는 더 심한지 봤어요.",
    )
    res.attach_to(
        "trend_deck.png",
        ch.line(
            "출시 후 성능 문제 언급 비율(전체 평균)",
            [ch.series("성능 문제 비중", trend.index, trend.values, 1)],
            xlabel="출시 후 개월",
            ylabel="부정 리뷰 중 비중",
            yunit="%",
            xunit="개월",
            zero=True,
        ),
        ch.bars(
            "기기별 성능 문제 리뷰",
            [
                {"label": "데스크톱", "value": rate.get("desktop"), "color": 6},
                {"label": "Steam Deck", "value": rate.get("deck"), "color": 3},
            ],
            unit="%",
        ),
    )

    # 그림 4: 성능 키워드
    ktop = kw.groupby("keyword")["count"].sum().sort_values(ascending=False)
    fig, ax = plt.subplots(figsize=(10, 3.6))
    ax.barh(ktop.index[::-1], (ktop / ktop.sum() * 100).values[::-1], color=style.PALETTE[2])
    ax.set(xlabel="성능 문제 언급 중 비중(%)", title="어떤 말이 가장 많이 나오나")
    ax.grid(axis="y", visible=False)
    res.fig(
        style.save(fig, out / "keywords.png"),
        "성능 문제 키워드",
        "ES에서 뽑은 성능 관련 키워드의 비중이에요. 게임 상세에는 그 게임의 상위 3개를 보여줘요.",
    )
    res.attach_to(
        "keywords.png",
        ch.bars(
            "성능 문제 키워드 비중",
            [{"label": k, "value": v / ktop.sum() * 100} for k, v in ktop.items()],
            unit="%",
            color=3,
        ),
    )

    bad = m[m.verdict == "bad"].sort_values("recent_share", ascending=False)
    tab = bad.assign(
        초기=bad.launch_share.round(0),
        최근=bad.recent_share.round(0),
        순위=bad.top_pct.map(lambda v: f"상위 {v:.0f}%"),
    )
    res.table(
        "사양표를 믿기 어려운 게임",
        tab[["name", "초기", "최근", "순위"]]
        .rename(columns={"name": "게임", "초기": "출시 초기(%)", "최근": f"최근 {WINDOW}개월(%)"})
        .head(10),
    )
    for r in bad.itertuples():
        res.tag(
            r.game_id,
            "spec_untrustworthy",
            "사양표 주의",
            "warn",
            f"최근 부정 리뷰의 {r.recent_share:.0f}%가 성능 문제예요",
        )

    cnt_v = m.verdict.value_counts()
    improving = int(((m.launch_share - m.recent_share >= 5) & m.launch_share.notna()).sum())
    res.takeaways += [
        f"게임 {len(m)}개 중 '믿기 어려워요' {int(cnt_v.get('bad', 0))}개, '주의' "
        f"{int(cnt_v.get('caution', 0))}개, "
        f"'신뢰할 만해요' {int(cnt_v.get('good', 0))}개, 판단 보류 "
        f"{int(cnt_v.get('hold', 0))}개예요.",
        f"출시 초기보다 성능 불만이 5%p 이상 줄어든 게임이 {improving}개예요 → 초기엔 문제였지만 "
        "지금은 나아진 게임을 가려낼 수 있어요.",
        f"출시 후 성능 문제 언급은 초기 대비 평균 {drop:.0f}% 줄어요. Steam Deck 리뷰의 언급은 "
        f"{rate.get('deck', float('nan'))}%로 "
        f"데스크톱 {rate.get('desktop', float('nan'))}%보다 높아요.",
        "이 지표는 리뷰 키워드로 본 참고 값이에요. 리뷰어가 권장 사양을 충족했는지는 반영하지 "
        "못해요.",
    ]
    res.api = {
        "window_months": WINDOW,
        "min_reviews": MIN_REVIEWS,
        "thresholds_pct": th,
        "rule": {
            "bad": f"최근 비율 ≥ max(상위 {100 - BAD_PCT}%, {BAD_FLOOR}%)",
            "caution": f"≥ max(상위 {100 - CAUTION_PCT}%, {CAUTION_FLOOR}%)",
        },
    }
    write_summary(res, out_root)
    return res
