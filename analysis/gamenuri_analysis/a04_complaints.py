"""④ 불만 유형 분석 — 사람들은 왜 싫어하나 (워드클라우드 발전형)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from matplotlib import pyplot as plt

from . import charts as ch
from . import style
from .dataset import Dataset
from .report import Result, fig_dir, write_summary

KEY = "complaints"
CATS = {
    "price": "가격",
    "optimization": "최적화",
    "server": "서버",
    "translation": "번역",
    "content": "콘텐츠 부족",
    "bug": "버그",
}
TOP_MIN_SHARE = 0.30  # 한 유형이 이 비율 이상이면 '○○ 불만형'


def _shares(c: pd.DataFrame) -> pd.DataFrame:
    p = c.pivot_table(index="game_id", columns="category", values="count", aggfunc="sum").reindex(
        columns=list(CATS)
    )
    return p.div(p.sum(axis=1), axis=0)


def run(d: Dataset, out_root: Path | None = None) -> Result:
    style.setup()
    out = fig_dir(KEY, out_root)
    res = Result(KEY, "불만 유형 분석", d.source)
    c = d.complaints
    sh = _shares(c)
    names = d.games.set_index("game_id").name
    res.dfs["shares"] = sh

    # 그림 1: 불만이 가장 많은 게임 10개의 구성비
    big = c.groupby("game_id")["count"].sum().nlargest(10).index
    top = sh.loc[big].join(names).set_index("name")[list(CATS)].iloc[::-1]
    fig, ax = plt.subplots(figsize=(10, 5.4))
    left = pd.Series(0.0, index=top.index)
    for i, (k, label) in enumerate(CATS.items()):
        ax.barh(
            top.index,
            top[k] * 100,
            left=left * 100,
            color=style.PALETTE[i],
            label=label,
            edgecolor="white",
        )
        for y, (v, l0) in enumerate(zip(top[k], left, strict=True)):
            if v >= 0.09:
                ax.text(
                    (l0 + v / 2) * 100,
                    y,
                    f"{v * 100:.0f}",
                    ha="center",
                    va="center",
                    color="white",
                    fontsize=8,
                )
        left += top[k]
    ax.set(
        xlim=(0, 100),
        xlabel="부정 리뷰 중 비중(%)",
        title="게임별 불만 유형 (부정 리뷰 키워드 기준)",
    )
    ax.legend(ncol=6, frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.14), fontsize=9)
    ax.grid(False)
    res.fig(
        style.save(fig, out / "stack.png"),
        "게임별 불만 유형",
        "ES 리뷰 인덱스(nori)에서 부정 리뷰 키워드를 유형별로 묶어 구성비를 냈어요. "
        "워드클라우드보다 ‘무엇이 문제인지’가 바로 보입니다.",
    )

    # 그림 2: 출시 후 시간에 따른 변화 (불만이 많은 게임 4개)
    focus: list[int] = []
    for cat in [
        "bug",
        "price",
        "translation",
        "optimization",
    ]:  # 유형마다 그 비중이 가장 큰 게임 1개씩
        pick = next(
            (g for g in sh.loc[big].sort_values(cat, ascending=False).index if g not in focus), None
        )
        if pick is not None:
            focus.append(pick)
    fig, axes = plt.subplots(2, 2, figsize=(10, 6), sharex=False)
    for ax, gid in zip(axes.ravel(), focus, strict=False):
        t = (
            c[c.game_id == gid]
            .pivot(index="month", columns="category", values="count")
            .reindex(columns=list(CATS))
        )
        t = (
            t.div(t.sum(axis=1), axis=0).mul(100).rolling(3, center=True, min_periods=1).mean()
        )  # 3개월 이동평균
        for i, k in enumerate(CATS):
            ax.plot(
                t.index,
                t[k],
                color=style.PALETTE[i],
                lw=2 if k in ("bug", "optimization", "price") else 1.2,
                label=CATS[k],
                alpha=1 if t[k].max() > 12 else 0.5,
            )
        ax.set(title=names[gid], xlabel="출시 후 개월", ylabel="비중(%)")
    axes[0, 0].legend(frameon=False, fontsize=7, ncol=2)
    res.fig(
        style.save(fig, out / "trend.png"),
        "출시 후 불만 유형 추이",
        "유형마다 그 비중이 가장 큰 게임을 골랐어요(3개월 이동평균). 버그·최적화 불만이 패치 뒤 "
        "줄어드는지 보세요.",
    )

    # 게임별 진단 + 태그
    rows = []
    for gid in sh.index:
        s = sh.loc[gid]
        tc = s.idxmax()
        m = c[c.game_id == gid].pivot(index="month", columns="category", values="count")
        mm = m.div(m.sum(axis=1), axis=0)
        improving = (
            len(mm) >= 6
            and (mm.loc[mm.index[:3], "bug"].mean() - mm.loc[mm.index[-3:], "bug"].mean())
            / max(mm.loc[mm.index[:3], "bug"].mean(), 1e-9)
            >= 0.5
        )
        rows.append((gid, names[gid], CATS[tc], round(s[tc] * 100), improving))
        if s[tc] >= TOP_MIN_SHARE:
            msg = {
                "price": (
                    "price_complaint",
                    "가격 불만형",
                    "info",
                    "할인 때 사면 만족할 게임이에요",
                ),
                "optimization": (
                    "opt_complaint",
                    "최적화 불만",
                    "warn",
                    "최적화 불만이 가장 많아요. 사양 여유를 두세요",
                ),
                "server": (
                    "server_complaint",
                    "서버 불만",
                    "warn",
                    "서버·접속 문제가 많아요. 안정화 뒤 구매를 권해요",
                ),
                "translation": (
                    "translation_complaint",
                    "번역 주의",
                    "warn",
                    "한국어 번역 불만이 많아요",
                ),
                "content": (
                    "content_complaint",
                    "콘텐츠 부족형",
                    "info",
                    "콘텐츠가 쌓인 뒤 구매를 권해요",
                ),
                "bug": ("bug_complaint", "버그 불만", "warn", "버그 불만이 많아요"),
            }[tc]
            if not (tc == "bug" and improving):
                res.tag(gid, msg[0], msg[1], msg[2], f"{CATS[tc]} {s[tc] * 100:.0f}% — {msg[3]}")
        if improving:
            res.tag(
                gid,
                "bug_improving",
                "버그 줄어드는 중",
                "good",
                "출시 초기보다 버그 불만이 절반 이하로 줄었어요. 지금은 사도 돼요",
            )
    diag = pd.DataFrame(
        rows, columns=["game_id", "게임", "최대 불만", "비중(%)", "버그 개선"]
    ).sort_values("비중(%)", ascending=False)
    res.table(
        "게임별 최대 불만 유형",
        diag.head(10)
        .drop(columns="game_id")
        .assign(**{"버그 개선": lambda x: x["버그 개선"].map({True: "개선 중", False: ""})}),
    )

    n_price = int((diag["최대 불만"].eq("가격") & diag["비중(%)"].ge(30)).sum())
    n_tr = int((diag["최대 불만"].eq("번역") & diag["비중(%)"].ge(30)).sum())
    res.takeaways += [
        f"불만이 한 유형에 30% 이상 몰린 게임은 {int((diag['비중(%)'] >= 30).sum())}개예요. 가격 "
        f"불만형 {n_price}개 → 할인 때 사면 만족해요.",
        f"버그 불만이 출시 초기의 절반 이하로 줄어든 게임은 {int(diag['버그 개선'].sum())}개 → "
        "지금은 사도 돼요.",
        f"한국어 번역 불만이 가장 큰 유형인 게임은 {n_tr}개 → 한국 유저에게 경고가 필요해요.",
    ]

    res.attach_to(
        "stack.png",
        ch.stacked(
            "게임별 불만 유형 (부정 리뷰 키워드 기준)",
            [{"key": k, "label": v} for k, v in CATS.items()],
            [
                {"label": nm, "values": {k: r[k] * 100 for k in CATS}}
                for nm, r in top.iloc[::-1].iterrows()
            ],
        ),
    )
    panels = []
    for gid in focus:
        tt = (
            c[c.game_id == gid]
            .pivot(index="month", columns="category", values="count")
            .reindex(columns=list(CATS))
        )
        tt = tt.div(tt.sum(axis=1), axis=0).mul(100).rolling(3, center=True, min_periods=1).mean()
        panels.append(
            ch.line(
                names[gid],
                [ch.series(CATS[k], tt.index, tt[k], i + 1) for i, k in enumerate(CATS)],
                xlabel="출시 후 개월",
                ylabel="비중(3개월 이동평균)",
                yunit="%",
                xunit="개월",
                zero=True,
            )
        )
    res.attach_to("trend.png", *panels)
    write_summary(res, out_root)
    return res
