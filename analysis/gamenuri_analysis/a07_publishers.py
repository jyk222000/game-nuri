"""⑦ 제작사·플랫폼 전략 — 이 회사 게임은 어떻게 팔리나."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from matplotlib import pyplot as plt

from . import charts as ch
from . import style
from .dataset import Dataset
from .report import Result, fig_dir, write_summary

KEY = "publishers"
MIN_GAMES = 3
FAST_DAYS = 200  # 이 안에 첫 할인이 오면 '기다리면 싸진다'


def run(d: Dataset, out_root: Path | None = None) -> Result:
    style.setup()
    out = fig_dir(KEY, out_root)
    res = Result(KEY, "제작사·플랫폼 전략", d.source)
    g = d.games
    cnt = g.publisher.value_counts()
    pubs = [p for p in cnt.index if cnt[p] >= MIN_GAMES and p != "기타 스튜디오"]

    first = (
        d.sale_events[(d.sale_events.store == "steam") & (d.sale_events.discount_pct >= 10)]
        .groupby("game_id")
        .start.min()
    )
    gg = g.set_index("game_id").join(first.rename("first_sale"))
    gg["first_days"] = (gg.first_sale - gg.pc_release).dt.days  # PC 출시일 기준
    stat = (
        gg[gg.publisher.isin(pubs)]
        .groupby("publisher")
        .agg(
            games=("name", "size"),
            score=("critic_score", "mean"),
            first_days=("first_days", "median"),
            no_sale=("first_sale", lambda s: s.isna().all()),
        )
        .sort_values("first_days")
    )
    res.dfs["stat"] = stat

    # 그림 1: 제작사별 장르 구성
    mix = (
        pd.crosstab(
            g[g.publisher.isin(pubs)].publisher, g[g.publisher.isin(pubs)].genre, normalize="index"
        )
        * 100
    )
    mix = mix.loc[stat.index[::-1]]
    fig, ax = plt.subplots(figsize=(10, 4.6))
    left = np.zeros(len(mix))
    for i, gn in enumerate(mix.columns):
        ax.barh(
            mix.index, mix[gn], left=left, color=style.PALETTE[i % 8], label=gn, edgecolor="white"
        )
        left += mix[gn].values
    ax.set(xlim=(0, 100), xlabel="게임 수 비중(%)", title="제작사별 장르 구성")
    ax.legend(ncol=7, frameon=False, fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.14))
    ax.grid(False)
    res.fig(
        style.save(fig, out / "genre_mix.png"),
        "제작사별 장르 구성",
        "제작사가 어떤 장르에 집중하는지 보여요. 팔로우할 제작사를 고르는 기준이 됩니다.",
    )

    # 그림 2: 평균 평점 + 첫 할인까지
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(10, 4.4), sharey=True)
    order = stat.index[::-1]
    a1.barh(order, stat.loc[order, "score"], color=style.PALETTE[0])
    a1.set(xlim=(60, 100), title="평균 평론 점수")
    for i, p in enumerate(order):
        a1.text(
            stat.loc[p, "score"] + 0.5, i, f"{stat.loc[p, 'score']:.0f}", va="center", fontsize=9
        )
    mx = np.nanmax(stat.first_days.values) if stat.first_days.notna().any() else 1
    for i, p in enumerate(order):
        r = stat.loc[p]
        if r.no_sale or pd.isna(r.first_days):
            a2.text(2, i, "거의 할인 안 함", va="center", fontsize=9, color=style.BAD)
        else:
            a2.barh(
                i, r.first_days, color=style.GOOD if r.first_days <= FAST_DAYS else style.PALETTE[5]
            )
            a2.text(r.first_days + mx * 0.01, i, f"{r.first_days:.0f}일", va="center", fontsize=9)
    a2.set(title="PC 출시 후 첫 할인까지(중앙값)", xlim=(0, mx * 1.2), xlabel="일")
    res.fig(
        style.save(fig, out / "score_first_sale.png"),
        "평균 평점 · 첫 할인까지 걸린 기간",
        "초록색은 출시 후 약 6개월 안에 첫 할인이 오는 제작사예요. 이런 회사 신작은 기다리면 "
        "싸집니다.",
    )

    # 그림 3: 콘솔 → PC 지연
    cons = gg[gg.console_release.notna()].copy()
    cons["delay"] = ((cons.pc_release - cons.console_release).dt.days / 30.4).round()
    exc = cons[cons.delay > 0].sort_values("delay")
    both = cons[cons.delay == 0]
    avg = exc.delay.mean()
    fig, ax = plt.subplots(figsize=(10, 4.4))
    allc = pd.concat([exc, both.nlargest(6, "regular_krw")]).sort_values(
        "delay"
    )  # 동시 출시는 대표 6개만
    ax.barh(
        allc.name,
        allc.delay.clip(lower=0.4),
        color=[style.PALETTE[2] if v > 0 else style.GOOD for v in allc.delay],
    )
    for i, v in enumerate(allc.delay):
        ax.text(
            max(v, 0.4) + 0.5, i, f"{v:.0f}개월" if v > 0 else "동시 출시", va="center", fontsize=8
        )
    if len(exc):
        ax.axvline(avg, color=style.MUTED, ls="--")
        ax.text(
            avg + 0.5, len(allc) - 0.6, f"독점작 평균 {avg:.0f}개월", color=style.MUTED, fontsize=9
        )
    ax.set(xlabel="콘솔 출시 → PC 출시까지(개월)", title="콘솔 독점작은 얼마 뒤 PC로 나오나")
    ax.tick_params(axis="y", labelsize=8)
    ax.grid(axis="y", visible=False)
    res.fig(
        style.save(fig, out / "console_delay.png"),
        "콘솔 → PC 출시 지연",
        "초록 = 동시 출시, 주황 = 콘솔 선출시 후 PC 이식. PC판을 기다릴지 콘솔을 살지 정하는 "
        "근거예요.",
    )

    show = stat.reset_index().assign(
        첫할인=lambda x: [
            ("거의 안 함" if n or pd.isna(v) else f"{v:.0f}일")
            for n, v in zip(x.no_sale, x.first_days, strict=True)
        ]
    )
    res.table(
        "제작사 비교",
        show[["publisher", "games", "score", "첫할인"]]
        .rename(
            columns={
                "publisher": "제작사",
                "games": "게임 수",
                "score": "평균 평점",
                "첫할인": "첫 할인까지",
            }
        )
        .round(0),
    )
    for gid, r in gg.iterrows():
        if r.publisher not in stat.index:
            continue
        s = stat.loc[r.publisher]
        if s.no_sale:
            res.tag(
                gid,
                "publisher_no_sale",
                "제작사: 정가 유지형",
                "warn",
                f"{r.publisher} 게임은 거의 할인하지 않아요",
            )
        elif s.first_days <= FAST_DAYS:
            res.tag(
                gid,
                "publisher_fast_sale",
                "제작사: 기다리면 싸짐",
                "info",
                f"{r.publisher} 게임은 출시 약 {s.first_days:.0f}일 만에 첫 할인이 와요",
            )

    fast = stat[(~stat.no_sale) & (stat.first_days <= FAST_DAYS)].index.tolist()
    res.takeaways += [
        f"출시 {FAST_DAYS}일 안에 첫 할인을 하는 제작사: {', '.join(fast) or '없음'}. 이 회사 "
        "신작은 기다리면 싸져요.",
        f"할인을 거의 하지 않는 제작사: {', '.join(stat[stat.no_sale].index) or '없음'}.",
        f"콘솔 선출시작은 평균 {avg / 12:.1f}년({avg:.0f}개월) 뒤 PC로 나와요 (표본 {len(exc)}개)."
        if len(exc)
        else "콘솔 선출시 사례가 부족해요.",
    ]

    res.attach_to(
        "genre_mix.png",
        ch.stacked(
            "제작사별 장르 구성",
            [{"key": gn, "label": gn} for gn in mix.columns],
            [{"label": p, "values": mix.loc[p].to_dict()} for p in mix.index[::-1]],
        ),
    )
    res.attach_to(
        "score_first_sale.png",
        ch.bars(
            "평균 평론 점수",
            [{"label": p, "value": stat.loc[p, "score"]} for p in stat.index],
            vmax=100,
        ),
        ch.bars(
            "PC 출시 후 첫 할인까지(중앙값)",
            [
                {
                    "label": p,
                    "value": None
                    if (stat.loc[p, "no_sale"] or pd.isna(stat.loc[p, "first_days"]))
                    else stat.loc[p, "first_days"],
                    "note": "거의 할인 안 함",
                    "color": 2 if stat.loc[p, "first_days"] <= FAST_DAYS else 6,
                }
                for p in stat.index
            ],
            unit="일",
        ),
    )
    res.attach_to(
        "console_delay.png",
        ch.bars(
            f"콘솔 → PC 출시 지연 (독점작 평균 {avg:.0f}개월)"
            if len(exc)
            else "콘솔 → PC 출시 지연",
            [
                {
                    "label": r["name"],
                    "value": r.delay,
                    "note": "동시 출시" if r.delay == 0 else None,
                    "color": 3 if r.delay > 0 else 2,
                }
                for _, r in allc.iloc[::-1].iterrows()
            ],
            unit="개월",
        ),
    )
    write_summary(res, out_root)
    return res
