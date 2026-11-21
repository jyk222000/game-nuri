"""⑥ 실제 플레이 패턴 — 끝까지 하는 게임인가."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from matplotlib import pyplot as plt

from . import charts as ch
from . import style
from .dataset import Dataset
from .report import Result, fig_dir, write_summary

KEY = "play-pattern"
HIST_GAMES = [119133, 1877, 135400, 150080]  # 대표 4개 (없으면 건너뜀)
QUIT_H = 5  # '금방 그만둔다' 기준 시간


def run(d: Dataset, out_root: Path | None = None) -> Result:
    style.setup()
    out = fig_dir(KEY, out_root)
    res = Result(KEY, "실제 플레이 패턴", d.source)
    g = d.games.set_index("game_id")
    pt = d.playtime
    med = pt.groupby("game_id").hours.median().rename("median_h")
    quit_pct = (
        pt.groupby("game_id").hours.apply(lambda s: (s < QUIT_H).mean() * 100).rename("quit_pct")
    )
    long_pct = (
        pt.groupby("game_id").hours.apply(lambda s: (s >= 20).mean() * 100).rename("long_pct")
    )
    t = g[["name", "ttb_hours", "ending_pct", "regular_krw"]].join(
        [med, quit_pct, long_pct], how="inner"
    )
    t["per_hour"] = (t.regular_krw / t.median_h).round()
    res.dfs["games"] = t

    # 그림 1: 클리어 시간 × 엔딩 달성률
    fig, ax = plt.subplots(figsize=(10, 4.8))
    ax.scatter(
        t.ttb_hours, t.ending_pct, s=55, alpha=0.8, color=style.PALETTE[0], edgecolor="white"
    )
    xs = np.linspace(t.ttb_hours.min(), t.ttb_hours.max(), 100)
    k, b = np.polyfit(t.ttb_hours, np.log(t.ending_pct.clip(lower=1)), 1)
    ax.plot(xs, np.exp(b + k * xs), color=style.PALETTE[2], lw=2, ls="--", label="지수 추세")
    for gid in HIST_GAMES:
        if gid in t.index:
            ax.annotate(
                t.loc[gid, "name"],
                (t.loc[gid, "ttb_hours"], t.loc[gid, "ending_pct"]),
                xytext=(6, 5),
                textcoords="offset points",
                fontsize=8,
            )
    ax.set(
        xlabel="IGDB 클리어 시간(시간)",
        ylabel="엔딩 업적 달성률(%)",
        title="클리어 시간이 길수록 엔딩까지 가는 사람이 줄어든다",
    )
    ax.legend(frameon=False)
    res.fig(
        style.save(fig, out / "ending_scatter.png"),
        "클리어 시간 × 엔딩 달성률",
        "Steam 전체 유저의 엔딩 업적 달성률과 IGDB 클리어 시간을 비교했어요.",
    )

    # 그림 2: 플레이 시간 분포
    show = [gid for gid in HIST_GAMES if gid in t.index]
    fig, axes = plt.subplots(1, len(show), figsize=(10, 3.6), sharey=True)
    bins = np.logspace(np.log10(0.1), np.log10(max(300, pt.hours.max())), 22)
    for ax, gid in zip(np.atleast_1d(axes), show, strict=True):
        h = pt[pt.game_id == gid].hours
        ax.hist(h, bins=bins, color=style.PALETTE[0], alpha=0.85)
        ax.axvline(QUIT_H, color=style.BAD, ls=":")
        ax.set_xscale("log")
        ax.set_xticks([0.1, 1, 10, 100, 1000], ["0.1", "1", "10", "100", "1000"])
        ax.minorticks_off()
        ax.set(
            title=f"{t.loc[gid, 'name']}\n5시간 내 {t.loc[gid, 'quit_pct']:.0f}%",
            xlabel="플레이 시간(시간, 로그)",
        )
        ax.title.set_fontsize(10)
    np.atleast_1d(axes)[0].set_ylabel("리뷰어 수")
    res.fig(
        style.save(fig, out / "playtime_hist.png"),
        "리뷰어 플레이 시간 분포",
        "봉우리가 두 개면 ‘금방 그만두는 사람’과 ‘오래 하는 사람’으로 갈린다는 뜻이에요. 점선은 "
        "5시간입니다.",
    )

    # 그림 3: 시간당 가격
    best = t.nsmallest(10, "per_hour").iloc[::-1]
    fig, ax = plt.subplots(figsize=(10, 4.4))
    ax.barh(best.name, best.per_hour, color=style.PALETTE[1])
    for i, v in enumerate(best.per_hour):
        ax.text(v + 10, i, f"{v:,.0f}원", va="center", fontsize=9)
    ax.set(xlabel="플레이 1시간당 정가(원)", title="가성비 TOP 10 — 정가 ÷ 리뷰어 중앙 플레이 시간")
    ax.grid(axis="y", visible=False)
    res.fig(
        style.save(fig, out / "cost_per_hour.png"),
        "플레이 시간당 가격",
        "낮을수록 같은 돈으로 오래 즐길 수 있는 게임이에요.",
    )

    split = t[(t.quit_pct >= 35) & (t.long_pct >= 25)]
    res.table(
        "중도 이탈이 많은 게임 (두 갈래형)",
        split.sort_values("quit_pct", ascending=False)
        .reset_index()[["name", "quit_pct", "long_pct", "median_h"]]
        .rename(
            columns={
                "name": "게임",
                "quit_pct": f"{QUIT_H}시간 내 이탈(%)",
                "long_pct": "20시간+ 유지(%)",
                "median_h": "중앙 플레이(h)",
            }
        )
        .round(0)
        .head(8),
    )
    for gid, r in split.iterrows():
        res.tag(
            gid,
            "early_quit",
            "중도 이탈 많음",
            "warn",
            f"구매자의 {r.quit_pct:.0f}%가 {QUIT_H}시간 안에 그만둬요",
        )
    for gid, r in best.tail(5).iterrows():
        res.tag(
            gid,
            "cheap_per_hour",
            "가성비",
            "good",
            f"리뷰어 중앙 {r.median_h:.0f}시간 플레이 · 시간당 약 {r.per_hour:,.0f}원",
        )

    short, long_ = t[t.ttb_hours < 20].ending_pct.mean(), t[t.ttb_hours >= 50].ending_pct.mean()
    res.takeaways += [
        f"클리어 20시간 미만 게임의 엔딩 달성률은 평균 {short:.0f}%, 50시간 이상은 "
        f"{long_:.0f}%예요 → 시간이 적다면 짧은 게임이 맞아요.",
        f"구매자 다수가 {QUIT_H}시간 안에 그만두는 두 갈래형 게임이 {len(split)}개 있어요.",
        f"가성비가 가장 좋은 게임은 {best.name.iloc[-1]}(시간당 약 "
        f"{best.per_hour.iloc[-1]:,.0f}원)예요.",
    ]

    res.attach_to(
        "ending_scatter.png",
        ch.scatter(
            "클리어 시간이 길수록 엔딩까지 가는 사람이 줄어든다",
            [
                {
                    "x": r.ttb_hours,
                    "y": r.ending_pct,
                    "label": r["name"] if gid in HIST_GAMES else None,
                }
                for gid, r in t.iterrows()
            ],
            xlabel="IGDB 클리어 시간",
            ylabel="엔딩 업적 달성률",
            xunit="시간",
            yunit="%",
            curve=[(x, float(np.exp(b + k * x))) for x in xs[::4]],
            curve_label="지수 추세",
        ),
    )
    panels = []
    for gid in show:
        cnt, edges = np.histogram(pt[pt.game_id == gid].hours, bins=bins)
        panels.append(
            ch.bars(
                f"{t.loc[gid, 'name']} — {QUIT_H}시간 내 {t.loc[gid, 'quit_pct']:.0f}%",
                [{"label": f"{edges[i]:.2g}", "value": int(cnt[i])} for i in range(len(cnt))],
                orient="v",
                xlabel="플레이 시간(시간, 로그 간격)",
                mark={
                    "pos": float(np.interp(QUIT_H, edges, range(len(edges)))),
                    "label": f"{QUIT_H}시간",
                },
            )
        )
    res.attach_to("playtime_hist.png", *panels)
    res.attach_to(
        "cost_per_hour.png",
        ch.bars(
            "가성비 TOP 10 — 정가 ÷ 리뷰어 중앙 플레이 시간",
            [{"label": r["name"], "value": r.per_hour} for _, r in best.iloc[::-1].iterrows()],
            unit="원",
            color=2,
        ),
    )
    write_summary(res, out_root)
    return res
