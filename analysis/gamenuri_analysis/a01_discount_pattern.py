"""① 할인 패턴 — 언제, 어디서, 얼마나 싸지나."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from matplotlib import pyplot as plt

from . import charts as ch
from . import style
from .dataset import Dataset
from .report import Result, fig_dir, write_summary

KEY = "discount-pattern"
STORE_LABEL = {
    "steam": "Steam",
    "epic": "Epic",
    "gog": "GOG",
    "humble": "Humble",
    "fanatical": "Fanatical",
    "gmg": "GMG",
    "gamesplanet": "Gamesplanet",
    "microsoft": "Microsoft",
    "danawa": "다나와(콘솔)",
}


def _monthly_best(d: Dataset) -> pd.DataFrame:
    """게임 × 출시 후 개월 → 그 달의 최대 할인율 (모든 스토어 중)."""
    ev = d.sale_events.merge(d.games[["game_id", "release_date", "tier"]], on="game_id")
    ev["month"] = ((ev.start - ev.release_date).dt.days / 30.4).astype(int)
    best = ev.groupby(["game_id", "tier", "month"], as_index=False).discount_pct.max()
    grid = pd.MultiIndex.from_product(
        [d.games.game_id, range(37)], names=["game_id", "month"]
    ).to_frame(index=False)
    grid = grid.merge(d.games[["game_id", "tier", "release_date"]], on="game_id")
    grid = grid[
        grid.release_date + pd.to_timedelta(grid.month * 30.4, unit="D") <= d.now
    ]  # 아직 안 온 달 제외
    return grid.merge(best.drop(columns="tier"), on=["game_id", "month"], how="left").fillna(
        {"discount_pct": 0}
    )


def _first_30_month(d: Dataset) -> pd.DataFrame:
    ev = d.sale_events[d.sale_events.discount_pct >= 30].merge(
        d.games[["game_id", "release_date", "tier"]], on="game_id"
    )
    first = (
        ev.groupby(["game_id", "tier"], as_index=False)
        .start.min()
        .merge(d.games[["game_id", "release_date"]], on="game_id")
    )
    first["months"] = (first.start - first.release_date).dt.days / 30.4
    return first


def _season_table(d: Dataset) -> pd.DataFrame:
    """스토어 × 월(1~12) 평균 할인율(할인 없는 날=0). 출시 12개월 이후 게임만."""
    days = pd.date_range("2024-01-01", d.now - pd.Timedelta(days=1))
    games = d.games[["game_id", "release_date"]]
    rows = []
    for store in STORE_LABEL:
        ev = d.sale_events[d.sale_events.store == store]
        if ev.empty:
            continue
        tot = np.zeros(12)
        cnt = np.zeros(12)
        for gm in games.itertuples():
            alive = days[(days - gm.release_date).days >= 365]
            if len(alive) == 0:
                continue
            disc = np.zeros(len(alive))
            for r in ev[ev.game_id == gm.game_id].itertuples():
                m = (alive >= r.start) & (alive < r.end)
                disc[m] = np.maximum(disc[m], r.discount_pct)
            mon = alive.month.values - 1
            np.add.at(tot, mon, disc)
            np.add.at(cnt, mon, 1)
        rows.append(pd.Series(np.where(cnt > 0, tot / np.maximum(cnt, 1), np.nan), name=store))
    return pd.DataFrame(rows).rename(columns=lambda c: f"{c + 1}월")


def _store_lead(d: Dataset) -> pd.DataFrame:
    first = (
        d.sale_events[d.sale_events.discount_pct >= 20]
        .groupby(["game_id", "store"], as_index=False)
        .agg(first=("start", "min"), depth=("discount_pct", "mean"))
    )
    steam = first[first.store == "steam"].set_index("game_id")
    rows = []
    for store, sub in first[first.store != "steam"].groupby("store"):
        j = sub.set_index("game_id").join(steam, rsuffix="_s", how="inner")
        if j.empty:
            continue
        rows.append(
            {
                "판매처": STORE_LABEL[store],
                "Steam보다 먼저(개월)": round(((j.first_s - j["first"]).dt.days / 30.4).mean(), 1),
                "평균 할인폭 차이(%p)": round((j.depth - j.depth_s).mean(), 1),
                "게임 수": len(j),
            }
        )
    return pd.DataFrame(rows).sort_values("Steam보다 먼저(개월)", ascending=False)


def run(d: Dataset, out_root: Path | None = None) -> Result:
    style.setup()
    out = fig_dir(KEY, out_root)
    res = Result(KEY, "할인 패턴", d.source)

    mb = _monthly_best(d)
    curve = mb.groupby(["tier", "month"], as_index=False).discount_pct.mean()
    first = _first_30_month(d)
    med = first.groupby("tier").months.median().round(1).to_dict()
    res.dfs.update(monthly_best=mb, first30=first)

    # 그림 1: 출시 후 경과 개월 × 할인율
    fig, ax = plt.subplots(figsize=(10, 4.6))
    for tier, color, name, ty in [
        ("aaa", style.PALETTE[0], "AAA", 3),
        ("indie", style.PALETTE[1], "인디", 9),
    ]:
        c = curve[curve.tier == tier]
        ax.plot(
            c.month,
            c.discount_pct,
            color=color,
            lw=2.4,
            label=f"{name} (n={int((d.games.tier == tier).sum())})",
        )
        if tier in med:
            ax.axvline(med[tier], color=color, ls=":", lw=1.4)
            ax.text(
                med[tier] + 0.3, ty, f"{name} 첫 30%↑ 중앙 {med[tier]}개월", color=color, fontsize=9
            )
    ax.axhline(30, color=style.MUTED, lw=0.8, ls="--")
    ax.set(
        xlabel="출시 후 경과 개월",
        ylabel="그 달 최대 할인율 평균(%)",
        title="출시 후 시간이 지날수록 할인이 깊어진다",
    )
    ax.legend(frameon=False)
    res.fig(
        style.save(fig, out / "curve.png"),
        "출시 후 경과 개월 × 할인율",
        "달마다 모든 스토어 중 가장 큰 할인율을 게임별로 구해 평균냈어요. 점선은 처음 30% 이상 "
        "할인이 나온 시점의 중앙값입니다.",
    )

    # 그림 2: 월 × 판매처 히트맵
    season = _season_table(d)
    fig, ax = plt.subplots(figsize=(10, 4.4))
    im = ax.imshow(season.values, cmap="Purples", aspect="auto")
    ax.set_xticks(range(12), season.columns)
    ax.set_yticks(range(len(season)), [STORE_LABEL[s] for s in season.index])
    ax.grid(False)
    for (i, j), v in np.ndenumerate(season.values):
        ax.text(
            j,
            i,
            f"{v:.0f}",
            ha="center",
            va="center",
            fontsize=8,
            color="white" if v > np.nanmax(season.values) * 0.6 else "#333",
        )
    fig.colorbar(im, ax=ax, label="평균 할인율(%)", shrink=0.8)
    ax.set_title("월 × 판매처 평균 할인율 (출시 12개월 이후 게임, 할인 없는 날=0%)")
    res.fig(
        style.save(fig, out / "heatmap.png"),
        "월 × 판매처 히트맵",
        "진할수록 그 달에 그 판매처가 더 깊게·자주 할인해요.",
    )

    # 그림 3: 판매처별 할인 시작 시점
    lead = _store_lead(d)
    res.table(
        "Steam 대비 판매처별 할인 시점·폭",
        lead,
        "처음 20% 이상 할인을 Steam보다 얼마나 일찍 시작했는지",
    )

    mean_by_month = season.mean().rename("v")
    hot = [int(m[:-1]) for m, v in mean_by_month.items() if v >= mean_by_month.median() * 1.25]
    res.takeaways += [
        f"첫 30% 이상 할인은 AAA 출시 약 {med.get('aaa', float('nan'))}개월, 인디 약 "
        f"{med.get('indie', float('nan'))}개월 무렵에 처음 나와요.",
        f"할인이 몰리는 달은 {', '.join(f'{m}월' for m in hot)}이에요 (세일 시즌).",
    ]
    if not lead.empty:
        top = lead.iloc[0]
        res.takeaways.append(
            f"{top['판매처']}은(는) Steam보다 평균 {top['Steam보다 먼저(개월)']}개월 먼저 할인을 "
            "시작해요."
        )

    # B: Backend 구매 타이밍 규칙
    res.api = {
        "first_30pct_month": {k: float(v) for k, v in med.items()},
        "expected_discount_by_age": {
            t: {int(m): round(float(v), 1) for m, v in zip(c.month, c.discount_pct, strict=True)}
            for t, c in curve.groupby("tier")
        },
        "sale_months": sorted(hot),
        "monthly_index": {m: round(float(v), 1) for m, v in mean_by_month.items()},
        "store_lead": json_rows(lead),
    }

    tiers = [("aaa", "AAA", 1), ("indie", "인디", 2)]
    res.attach_to(
        "curve.png",
        ch.line(
            "출시 후 경과 개월 × 할인율",
            [
                ch.series(
                    f"{n} (n={int((d.games.tier == t).sum())})",
                    curve[curve.tier == t].month,
                    curve[curve.tier == t].discount_pct,
                    ci,
                )
                for t, n, ci in tiers
            ],
            xlabel="출시 후 경과 개월",
            ylabel="그 달 최대 할인율 평균",
            yunit="%",
            xunit="개월",
            zero=True,
            vlines=[
                {"x": med[t], "label": f"{n} 첫 30%↑ 중앙 {med[t]}개월", "color": ci}
                for t, n, ci in tiers
                if t in med
            ],
            hlines=[{"y": 30, "label": "30%"}],
        ),
    )
    res.attach_to(
        "heatmap.png",
        ch.heatmap(
            "월 × 판매처 평균 할인율 (출시 12개월 이후 게임, 할인 없는 날=0%)",
            [STORE_LABEL[s] for s in season.index],
            list(season.columns),
            season.values,
        ),
    )
    write_summary(res, out_root)
    return res


def json_rows(df: pd.DataFrame) -> list[dict[str, object]]:
    return df.to_dict(orient="records")
