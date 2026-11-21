"""③ 평론 점수 vs 유저 평가 — 누구 말을 믿어야 하나."""

from __future__ import annotations

from pathlib import Path

from matplotlib import pyplot as plt

from . import charts as ch
from . import style
from .dataset import Dataset
from .report import Result, fig_dir, write_summary

KEY = "critic-vs-user"
GAP = 10  # 이 이상 차이 나면 꼬리표


def run(d: Dataset, out_root: Path | None = None) -> Result:
    style.setup()
    out = fig_dir(KEY, out_root)
    res = Result(KEY, "평론 점수 vs 유저 평가", d.source)
    g = d.games.copy()
    g["gap"] = g.positive_pct - g.critic_score
    res.dfs["games"] = g

    genres = g.genre.value_counts().index.tolist()
    palette = [*style.PALETTE, "#f0b429", "#2b8a3e"]
    color = {gn: palette[i % 8] for i, gn in enumerate(genres)}

    fig, ax = plt.subplots(figsize=(10, 5.4))
    ax.plot([55, 100], [55, 100], color=style.MUTED, ls="--", lw=1)
    ax.text(86, 80.5, "평론 = 유저", color=style.MUTED, fontsize=9, rotation=33)
    for gn, sub in g.groupby("genre"):
        ax.scatter(
            sub.critic_score,
            sub.positive_pct,
            s=55,
            alpha=0.8,
            color=color.get(gn, "#bbb"),
            edgecolor="white",
            label=f"{gn} ({len(sub)})",
        )
    out_g = g[g.gap.abs() >= GAP].sort_values("gap")
    for r in out_g.head(4).itertuples():
        ax.annotate(
            r.name,
            (r.critic_score, r.positive_pct),
            xytext=(6, -12),
            textcoords="offset points",
            fontsize=8,
            color=style.BAD,
        )
    for r in out_g.tail(5).itertuples():
        ax.annotate(
            r.name,
            (r.critic_score, r.positive_pct),
            xytext=(6, 5),
            textcoords="offset points",
            fontsize=8,
            color=style.GOOD,
        )
    ax.set(
        xlabel="평론 점수",
        ylabel="Steam 긍정률(%)",
        xlim=(58, 100),
        ylim=(40, 101),
        title="평론 점수 × 유저 긍정률 (점선 위 = 유저가 더 후함)",
    )
    ax.legend(frameon=False, fontsize=8, ncol=2, loc="lower right")
    res.fig(
        style.save(fig, out / "scatter.png"),
        "평론 점수 × Steam 긍정률",
        f"점 하나가 게임 하나예요. 대각선에서 {GAP}점 이상 벗어난 게임은 이름을 "
        "달았습니다(초록=유저가 더 후함, 빨강=평론이 더 후함).",
    )

    by_genre = g.groupby("genre").gap.agg(["mean", "size"]).query("size >= 3").sort_values("mean")
    by_tier = g.groupby("tier")[["early_positive_pct", "positive_pct"]].mean().round(1)
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(10, 4.2), gridspec_kw={"width_ratios": [1.4, 1]})
    a1.barh(
        by_genre.index,
        by_genre["mean"],
        color=[style.GOOD if v > 0 else style.BAD for v in by_genre["mean"]],
    )
    a1.axvline(0, color="#444", lw=0.8)
    for i, v in enumerate(by_genre["mean"]):
        a1.text(max(v, 0) + 0.3, i, f"{v:+.1f}", va="center", ha="left", fontsize=9)
    a1.set(title="장르별 (유저 - 평론) 평균 차이", xlabel="점")
    x = range(len(by_tier))
    a2.bar(
        [i - 0.2 for i in x],
        by_tier.early_positive_pct,
        0.4,
        label="출시 초기",
        color=style.PALETTE[5],
    )
    a2.bar([i + 0.2 for i in x], by_tier.positive_pct, 0.4, label="현재", color=style.PALETTE[0])
    a2.set_xticks(list(x), ["AAA" if t == "aaa" else "인디" for t in by_tier.index])
    a2.set(title="출시 초기 vs 현재 긍정률", ylabel="%", ylim=(50, 100))
    a2.legend(frameon=False)
    res.fig(
        style.save(fig, out / "genre_gap.png"),
        "장르별 차이 · 초기 대비 현재",
        "장르마다 평론과 유저 중 누가 더 후한지, 출시 초기에서 지금까지 평가가 어떻게 바뀌었는지 "
        "봤어요.",
    )

    tab = out_g.sort_values("gap", ascending=False)[
        ["name", "genre", "critic_score", "positive_pct", "gap"]
    ]
    tab = tab.assign(꼬리표=["숨은 명작" if v > 0 else "과대평가" for v in tab.gap])
    res.table(
        f"차이가 큰 게임 (±{GAP}점 이상)",
        tab.rename(
            columns={
                "name": "게임",
                "genre": "장르",
                "critic_score": "평론",
                "positive_pct": "유저 긍정률(%)",
                "gap": "차이",
            }
        ),
    )
    for r in out_g.itertuples():
        if r.gap > 0:
            res.tag(
                r.game_id,
                "hidden_gem",
                "숨은 명작",
                "good",
                f"평론 {r.critic_score}점보다 유저 긍정률 {r.positive_pct}%가 높아요",
            )
        else:
            res.tag(
                r.game_id,
                "overrated",
                "과대평가 주의",
                "warn",
                f"평론 {r.critic_score}점에 비해 유저 긍정률은 {r.positive_pct}%예요",
            )

    hi, lo = by_genre.iloc[-1], by_genre.iloc[0]
    res.takeaways += [
        f"유저가 평론보다 가장 후한 장르는 {by_genre.index[-1]}({hi['mean']:+.1f}점), 가장 박한 "
        f"장르는 {by_genre.index[0]}({lo['mean']:+.1f}점)이에요.",
        f"±{GAP}점 이상 차이 나는 게임은 숨은 명작 {int((out_g.gap > 0).sum())}개, 과대평가 "
        f"{int((out_g.gap < 0).sum())}개예요.",
        "출시 초기 → 현재 긍정률: "
        + ", ".join(
            f"{'AAA' if t == 'aaa' else '인디'} {r.early_positive_pct:.0f}→{r.positive_pct:.0f}%"
            for t, r in by_tier.iterrows()
        )
        + ".",
    ]

    labelled = set(out_g.head(4).name) | set(out_g.tail(5).name)
    res.attach_to(
        "scatter.png",
        ch.scatter(
            "평론 점수 × 유저 긍정률 (점선 위 = 유저가 더 후함)",
            [
                {
                    "x": r.critic_score,
                    "y": r.positive_pct,
                    "group": r.genre,
                    "label": r.name if r.name in labelled else None,
                }
                for r in g.itertuples()
            ],
            groups=[{"name": gn, "color": i % 8 + 1} for i, gn in enumerate(genres)],
            xlabel="평론 점수",
            ylabel="Steam 긍정률",
            yunit="%",
            xlim=(58, 100),
            ylim=(40, 101),
            diagonal=True,
        ),
    )
    res.attach_to(
        "genre_gap.png",
        ch.bars(
            "장르별 (유저 - 평론) 평균 차이",
            [{"label": k, "value": v} for k, v in by_genre["mean"].iloc[::-1].items()],
            unit="점",
        ),
        ch.bars(
            "출시 초기 vs 현재 긍정률",
            [
                {"label": f"{'AAA' if t == 'aaa' else '인디'} {nm}", "value": r[col], "color": ci}
                for t, r in by_tier.iterrows()
                for nm, col, ci in [("초기", "early_positive_pct", 6), ("현재", "positive_pct", 1)]
            ],
            unit="%",
            vmax=100,
        ),
    )
    write_summary(res, out_root)
    return res
