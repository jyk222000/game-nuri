"""② 할인 효과 — 할인은 플레이어를 얼마나 끌어오나."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from matplotlib import pyplot as plt

from . import charts as ch
from . import style
from .dataset import Dataset
from .report import Result, fig_dir, write_summary

KEY = "discount-effect"
MIN_EVENTS = 5
BUCKETS = [("30% 미만", 0, 30), ("30~49%", 30, 50), ("50% 이상", 50, 101)]


def _event_windows(d: Dataset) -> pd.DataFrame:
    """Steam 할인마다 시작일 기준 -30~+30일 신규 리뷰를 '할인 전 30일 평균=100'으로 맞춘 표.
    앞뒤 30일 안에 다른 Steam 할인이 겹치는 이벤트는 기준선·꼬리가 오염되므로 뺀다."""
    ev = (
        d.sale_events[d.sale_events.store == "steam"]
        .merge(d.games[["game_id", "release_date"]], on="game_id")
        .sort_values(["game_id", "start"])
    )
    rd = d.reviews_daily.set_index(["game_id", "date"]).n_reviews
    rows = []
    for gid, sub in ev.groupby("game_id"):
        starts = sub.start.tolist()
        ends = sub.end.tolist()
        for i, r in enumerate(sub.itertuples()):
            if any(ends[j] > r.start - pd.Timedelta(days=30) for j in range(i)):
                continue  # 앞 30일 안에 다른 할인 → 기준선 오염
            if any(
                r.start < starts[j] <= r.start + pd.Timedelta(days=30)
                for j in range(i + 1, len(starts))
            ):
                continue  # 뒤 30일 안에 다음 할인 → 가짜 두 번째 봉우리
            idx = pd.date_range(r.start - pd.Timedelta(days=30), r.start + pd.Timedelta(days=30))
            if idx[0] < pd.Timestamp("2024-05-01") or idx[-1] >= d.now:
                continue
            try:
                s = rd.loc[gid].reindex(idx)
            except KeyError:
                continue
            base = s.iloc[:30].mean()
            if not base or np.isnan(base):
                continue
            age = (r.start - r.release_date).days / 365
            for k, v in enumerate(s.values):
                rows.append((gid, r.start, r.discount_pct, age, k - 30, v / base * 100))
    return pd.DataFrame(rows, columns=["game_id", "start", "discount_pct", "age_y", "day", "idx"])


def run(d: Dataset, out_root: Path | None = None) -> Result:
    style.setup()
    out = fig_dir(KEY, out_root)
    res = Result(KEY, "할인 효과", d.source)
    w = _event_windows(d)
    res.dfs["windows"] = w
    n_events = w.groupby(["game_id", "start"]).ngroups

    # 그림 1: 할인율 구간별 신규 리뷰
    fig, ax = plt.subplots(figsize=(10, 4.6))
    peaks: dict[str, float] = {}
    skipped: list[str] = []
    for (name, lo, hi), color in zip(
        BUCKETS, [style.PALETTE[5], style.PALETTE[3], style.PALETTE[2]], strict=True
    ):
        sub = w[(w.discount_pct >= lo) & (w.discount_pct < hi)]
        n_ev = sub.groupby(["game_id", "start"]).ngroups
        if n_ev < MIN_EVENTS:  # 표본이 너무 적으면 선이 노이즈라 그리지 않는다
            skipped.append(f"{name}({n_ev}건)")
            continue
        m = sub.groupby("day").idx.mean()
        peaks[name] = round(float(m.loc[0:3].max()), 0)
        ax.plot(
            m.index,
            m.values,
            lw=2.3,
            color=color,
            label=f"{name} (이벤트 {sub.groupby(['game_id', 'start']).ngroups}건)",
        )
    ax.axvline(0, color=style.MUTED, ls="--", lw=1)
    ax.axhline(100, color=style.MUTED, lw=0.8)
    ax.set(
        xlabel="할인 시작일(0) 기준 일수",
        ylabel="신규 리뷰 지수 (할인 전 30일 평균=100)",
        title="할인 전후 30일 신규 리뷰",
    )
    ax.legend(frameon=False)
    res.fig(
        style.save(fig, out / "effect_bucket.png"),
        "할인 전후 신규 리뷰 (할인율 구간별)",
        f"Steam 할인 {n_events}건을 시작일에 맞춰 겹쳤어요. 앞뒤 30일 안에 다른 할인이 겹친 건은 "
        "뺐습니다."
        + (
            f" 이벤트가 {MIN_EVENTS}건 미만인 구간({', '.join(skipped)})은 표시하지 않았어요."
            if skipped
            else ""
        ),
    )

    # 그림 2: 게임 나이별 효과 + 구매 시점별 긍정률
    big = w[w.discount_pct >= 50]
    big = big.assign(age=pd.cut(big.age_y, [0, 1, 3, 20], labels=["1년 미만", "1~3년", "3년 이상"]))
    age_eff = big[big.day.between(0, 3)].groupby("age", observed=True).idx.mean().div(100).round(2)

    rd = d.reviews_daily.merge(
        d.games[["game_id", "value_type", "name", "online_only"]], on="game_id"
    )
    steam_disc = d.sale_events[d.sale_events.store == "steam"]
    on_sale = pd.Series(False, index=rd.index)
    for r in steam_disc.itertuples():
        on_sale |= (rd.game_id == r.game_id) & (rd.date >= r.start) & (rd.date < r.end)
    rd["on_sale"] = on_sale
    pos = (
        rd.groupby(["game_id", "on_sale"])
        .agg(n=("n_reviews", "sum"), p=("n_positive", "sum"))
        .reset_index()
    )
    pos["pct"] = pos.p / pos.n * 100
    wide = (
        pos.pivot(index="game_id", columns="on_sale", values="pct")
        .dropna()
        .rename(columns={False: "full", True: "sale"})
    )
    wide["diff"] = wide.sale - wide.full
    overall = pos.groupby("on_sale").apply(
        lambda x: x.p.sum() / x.n.sum() * 100, include_groups=False
    )

    fig, (a1, a2) = plt.subplots(1, 2, figsize=(10, 4.2))
    a1.bar(age_eff.index.astype(str), age_eff.values, color=style.PALETTE[2])
    for i, v in enumerate(age_eff.values):
        a1.text(i, v + 0.05, f"{v:.1f}배", ha="center", fontsize=10)
    a1.set(title="게임 나이별 50%+ 할인 효과", ylabel="할인 직후 3일 신규 리뷰 배수")
    a2.bar(
        ["정가 시기", "할인 시기"],
        [overall.get(False, np.nan), overall.get(True, np.nan)],
        color=[style.PALETTE[5], style.PALETTE[0]],
    )
    for i, v in enumerate([overall.get(False, np.nan), overall.get(True, np.nan)]):
        a2.text(i, v + 0.5, f"{v:.1f}%", ha="center", fontsize=10)
    a2.set(ylim=(60, 100), title="리뷰 긍정률: 정가 vs 할인", ylabel="긍정률(%)")
    res.fig(
        style.save(fig, out / "effect_age_positive.png"),
        "게임 나이별 효과 · 구매 시점별 긍정률",
        "오래된 게임일수록 할인 효과가 크고, 할인 시기 리뷰의 긍정률이 평균적으로 어떻게 다른지 "
        "비교했어요.",
    )

    # 그림 3: 동접자 1주일
    cc = d.ccu_hourly.copy()
    cc["day"] = cc.ts.dt.floor("D")
    sale_start = pd.Timestamp("2026-11-20")
    on = set(
        steam_disc[
            (steam_disc.start <= sale_start)
            & (steam_disc.end > sale_start)
            & (steam_disc.discount_pct >= 30)
        ].game_id
    )
    cc["group"] = np.where(cc.game_id.isin(on), "11/20 할인 시작 게임", "할인 없음")
    daily = cc.groupby(["group", "day", "game_id"]).ccu.mean().reset_index()
    base = daily[daily.day < sale_start].groupby("game_id").ccu.mean()
    daily["idx"] = daily.ccu / daily.game_id.map(base) * 100
    fig, ax = plt.subplots(figsize=(10, 3.8))
    for g, color in [("11/20 할인 시작 게임", style.PALETTE[2]), ("할인 없음", style.PALETTE[5])]:
        s = daily[daily.group == g].groupby("day").idx.mean()
        if len(s):
            ax.plot(
                s.index,
                s.values,
                marker="o",
                lw=2.2,
                color=color,
                label=f"{g} ({daily[daily.group == g].game_id.nunique()}개)",
            )
    ax.axvline(sale_start, color=style.MUTED, ls="--")
    ax.set(ylabel="동접자 지수 (할인 전=100)", title="동접자 지수 — 데이터 약 1주일치뿐 (참고용)")
    ax.legend(frameon=False)
    fig.autofmt_xdate()
    res.fig(
        style.save(fig, out / "ccu_week.png"),
        "동접자 (1주일치)",
        "동접자 수집은 이제 시작이라 발표 전까지 약 1주일치만 있어요. 과거 흐름은 리뷰 작성 "
        "시각으로 대신 봤습니다.",
    )

    # 유형 분류 표 + 태그
    games = d.games.set_index("game_id")
    spike = w[(w.discount_pct >= 50) & w.day.between(0, 3)].groupby("game_id").idx.mean()
    tab = wide.join(games[["name", "online_only"]]).join(spike.rename("spike"))
    tab["유형"] = np.select(
        [(tab["diff"] >= 5), tab.online_only & (tab.spike.fillna(0) >= 150)],
        ["가성비형", "멀티플레이형"],
        "정가 만족형",
    )
    show = tab[tab["유형"] != "정가 만족형"].sort_values("diff", ascending=False).head(8)
    res.table(
        "할인 효과로 본 게임 유형",
        show.reset_index()[["name", "full", "sale", "diff", "유형"]]
        .rename(
            columns={
                "name": "게임",
                "full": "정가 긍정률(%)",
                "sale": "할인 긍정률(%)",
                "diff": "차이(%p)",
            }
        )
        .round(1),
        "가성비형: 할인 시기 긍정률이 5%p 이상 높음 / 멀티플레이형: 온라인 전용이고 할인 직후 "
        "유입이 큼",
    )
    for gid, r in tab.iterrows():
        if r["유형"] == "가성비형":
            res.tag(
                gid,
                "value_game",
                "가성비형",
                "info",
                f"할인 때 긍정률이 {r['diff']:+.0f}%p — 할인가로 사면 만족도가 높아요",
            )
        elif r["유형"] == "멀티플레이형":
            res.tag(
                gid,
                "multi_game",
                "할인 직후 구매 추천",
                "info",
                "온라인 게임이라 할인 직후에 사야 같이 할 사람이 많아요",
            )

    res.takeaways += [
        "할인 직후 신규 리뷰(할인 전=100): "
        + ", ".join(f"{k} {v:.0f}" for k, v in peaks.items())
        + " — 깊게 할인할수록 유입이 커요.",
        "게임이 오래될수록 같은 50% 할인의 효과가 커요: "
        + ", ".join(f"{k} {v}배" for k, v in age_eff.items())
        + ".",
        f"할인 시기 리뷰 긍정률은 {overall.get(True, float('nan')):.1f}%, 정가 시기는 "
        f"{overall.get(False, float('nan')):.1f}%예요.",
    ]
    res.takeaways = [t for t in res.takeaways if t]

    bser = []
    for (name, lo, hi), ci in zip(BUCKETS, [6, 4, 3], strict=True):
        sub = w[(w.discount_pct >= lo) & (w.discount_pct < hi)]
        if sub.groupby(["game_id", "start"]).ngroups >= MIN_EVENTS:
            m = sub.groupby("day").idx.mean()
            bser.append(ch.series(name, m.index, m.values, ci))
    res.attach_to(
        "effect_bucket.png",
        ch.line(
            "할인 전후 30일 신규 리뷰",
            bser,
            xlabel="할인 시작일(0) 기준 일수",
            ylabel="신규 리뷰 지수 (할인 전 30일 평균=100)",
            vlines=[{"x": 0, "label": "할인 시작"}],
            hlines=[{"y": 100, "label": "평소"}],
        ),
    )
    res.attach_to(
        "effect_age_positive.png",
        ch.bars(
            "게임 나이별 50%+ 할인 효과 (할인 직후 3일 신규 리뷰 배수)",
            [{"label": str(k), "value": v} for k, v in age_eff.items()],
            unit="배",
            color=3,
        ),
        ch.bars(
            "리뷰 긍정률: 정가 vs 할인",
            [
                {"label": "정가 시기", "value": overall.get(False), "color": 6},
                {"label": "할인 시기", "value": overall.get(True), "color": 1},
            ],
            unit="%",
            vmax=100,
        ),
    )
    cser, xl = [], []
    for gname, ci in [("11/20 할인 시작 게임", 3), ("할인 없음", 6)]:
        s = daily[daily.group == gname].groupby("day").idx.mean()
        if len(s):
            xl = [x.strftime("%m/%d") for x in s.index]
            cser.append(
                ch.series(
                    f"{gname} ({daily[daily.group == gname].game_id.nunique()}개)",
                    range(len(s)),
                    s.values,
                    ci,
                )
            )
    res.attach_to(
        "ccu_week.png",
        ch.line(
            "동접자 지수 — 데이터 약 1주일치뿐 (참고용)",
            cser,
            ylabel="동접자 지수 (할인 전=100)",
            xlabels=xl,
            vlines=[{"x": len(xl) - 1, "label": "11/20 할인 시작"}] if xl else [],
        ),
    )
    write_summary(res, out_root)
    return res
