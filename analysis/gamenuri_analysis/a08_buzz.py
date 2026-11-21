"""⑧ 화제성 분석 — 지금 뜨는 게임은 왜 뜨나."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from matplotlib import pyplot as plt

from . import charts as ch
from . import style
from .dataset import Dataset
from .report import Result, fig_dir, write_summary

KEY = "buzz"
SURGE, COOL = 140, 120  # 화제성 지수가 이 이상이면 급상승, 이 미만이면 식음
KIND = {"sale": "할인", "update": "업데이트", "dlc": "DLC·발표", "unknown": "원인 불명"}
KCOLOR = {"sale": style.PALETTE[1], "update": style.PALETTE[2], "dlc": style.PALETTE[3]}
FOCUS = [150080, 135400]


def _index(d: Dataset) -> pd.DataFrame:
    """화제성 지수 = 동접·신규 리뷰가 직전 14일 중앙값의 몇 배인지 평균 ×100."""
    out = []
    for gid, s in d.buzz_daily.sort_values("date").groupby("game_id"):
        s = s.set_index("date")
        ci = s.ccu / s.ccu.shift(1).rolling(14).median()
        ri = s.new_reviews / s.new_reviews.shift(1).rolling(14).median()
        out.append(
            pd.DataFrame(
                {"game_id": gid, "date": s.index, "idx": (0.5 * ci + 0.5 * ri).values * 100}
            )
        )
    return pd.concat(out, ignore_index=True).dropna()


def _surges(d: Dataset, idx: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for gid, s in idx.groupby("game_id"):
        s = s.set_index("date").idx
        ev = d.buzz_events[d.buzz_events.game_id == gid]
        i, dates = 0, s.index
        while i < len(s):
            if s.iloc[i] >= SURGE and (i == 0 or s.iloc[i - 1] < SURGE):
                start = dates[i]
                near = ev[
                    (ev.date >= start - pd.Timedelta(days=1))
                    & (ev.date <= start + pd.Timedelta(days=1))
                ]
                cause = near.type.iloc[0] if len(near) else "unknown"
                win = s.iloc[i : i + 40]
                peak = win.iloc[:6].max() - 100
                half = next(
                    (k for k, v in enumerate(win.values) if k > 0 and v - 100 <= peak * 0.5), None
                )
                end = next(
                    (dates[i + k] for k, v in enumerate(win.values) if k > 0 and v < COOL), None
                )
                nxt = (
                    ev[(ev.type == "sale") & (ev.date > (end or start))].date.min()
                    if end is not None
                    else pd.NaT
                )
                rows.append(
                    (
                        gid,
                        start,
                        cause,
                        peak + 100,
                        half,
                        (nxt - end).days if pd.notna(nxt) and end is not None else np.nan,
                    )
                )
                i += 7
            else:
                i += 1
    return pd.DataFrame(
        rows, columns=["game_id", "start", "cause", "peak", "half_life", "lag_to_sale"]
    )


def run(d: Dataset, out_root: Path | None = None) -> Result:
    style.setup()
    out = fig_dir(KEY, out_root)
    res = Result(KEY, "화제성 분석", d.source)
    idx = _index(d)
    sg = _surges(d, idx)
    res.dfs.update(index=idx, surges=sg)
    names = d.games.set_index("game_id").name

    # 그림 1: 타임라인 (두 게임)
    focus = [g for g in FOCUS if g in set(idx.game_id)] or list(idx.game_id.unique()[:2])
    fig, axes = plt.subplots(len(focus), 1, figsize=(10, 3.6 * len(focus)), sharex=True)
    for ax, gid in zip(np.atleast_1d(axes), focus, strict=True):
        s = idx[idx.game_id == gid].set_index("date").idx
        ax.plot(s.index, s.values, color=style.PALETTE[0], lw=1.8)
        ax.axhline(100, color=style.MUTED, lw=0.8)
        ev = d.buzz_events[
            (d.buzz_events.game_id == gid)
            & d.buzz_events.date.between(s.index.min(), s.index.max())
        ]
        for r in ev.itertuples():
            ax.axvline(r.date, color=KCOLOR[r.type], ls=":", lw=1.2)
        ax.set(ylabel="화제성 지수", title=names[gid])
    handles = [plt.Line2D([0], [0], color=c, ls=":", label=KIND[k]) for k, c in KCOLOR.items()]
    np.atleast_1d(axes)[0].legend(
        handles=handles, frameon=False, ncol=3, loc="lower right", bbox_to_anchor=(1, 1.0)
    )
    res.fig(
        style.save(fig, out / "timeline.png"),
        "화제성 지수 추이와 사건",
        "동접자·신규 리뷰 증가율로 만든 지수(평소=100)예요. 점선은 할인·업데이트·DLC 발표 "
        "시점입니다.",
    )

    # 그림 2: 원인 비율 + 반감기
    share = sg.cause.value_counts(normalize=True).mul(100).reindex(list(KIND)).fillna(0)
    hl = sg.groupby("cause").half_life.median().reindex(["sale", "update", "dlc"])
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(10, 4.2))
    a1.barh([KIND[k] for k in share.index][::-1], share.values[::-1], color=style.PALETTE[0])
    for i, v in enumerate(share.values[::-1]):
        a1.text(v + 1, i, f"{v:.0f}%", va="center")
    a1.set(title=f"급상승 {len(sg)}건의 원인", xlabel="%")
    a2.bar([KIND[k] for k in hl.index], hl.values, color=[KCOLOR[k] for k in hl.index])
    for i, v in enumerate(hl.values):
        a2.text(
            i, (v if pd.notna(v) else 0) + 0.3, f"{v:.0f}일" if pd.notna(v) else "-", ha="center"
        )
    a2.set_ylim(0, float(np.nanmax(hl.values)) * 1.3)
    a2.set(title="화제성이 절반으로 식는 데 걸린 기간(중앙값)", ylabel="일")
    res.fig(
        style.save(fig, out / "cause_halflife.png"),
        "급상승의 원인 · 지속 기간",
        "할인으로 오른 화제성은 빨리 식고, 업데이트로 오른 화제성은 오래가는지 확인해요.",
    )

    # 지금 뜨는 게임
    last = (
        idx.sort_values("date")
        .groupby("game_id")
        .tail(1)
        .sort_values("idx", ascending=False)
        .head(5)
    )
    rows = []
    for r in last.itertuples():
        ev = d.buzz_events[
            (d.buzz_events.game_id == r.game_id)
            & (d.buzz_events.date <= r.date)
            & (d.buzz_events.date >= r.date - pd.Timedelta(days=14))
        ].sort_values("date")
        cause = ev.type.iloc[-1] if len(ev) else "unknown"
        exp = hl.get(cause, np.nan)
        rows.append(
            (
                names[r.game_id],
                round(r.idx),
                KIND[cause],
                f"약 {exp:.0f}일" if pd.notna(exp) else "-",
            )
        )
    res.table(
        "지금 뜨는 게임 (화제성 지수 상위)",
        pd.DataFrame(rows, columns=["게임", "화제성 지수", "원인", "예상 지속"]),
        "최근 14일 안에 있었던 사건을 원인으로 보고, 같은 원인의 과거 반감기를 예상 지속 기간으로 "
        "썼어요.",
    )

    lag = sg.lag_to_sale.median()
    top = share.drop("unknown").idxmax()
    res.takeaways += [
        f"급상승의 {share[top]:.0f}%는 ‘{KIND[top]}’ 때문이에요.",
        "화제성이 절반으로 식는 기간(중앙값): "
        + ", ".join(f"{KIND[k]} {v:.0f}일" for k, v in hl.items() if pd.notna(v))
        + ".",
        f"화제성이 식은 뒤 다음 할인까지는 중앙값 {lag:.0f}일이에요 → 화제성이 지나간 뒤 할인을 "
        "기다리는 전략이 가능해요."
        if pd.notna(lag)
        else "",
    ]
    res.takeaways = [t for t in res.takeaways if t]

    cidx = {"sale": 2, "update": 3, "dlc": 4}
    panels = []
    for gid in focus:
        s = idx[idx.game_id == gid].set_index("date").idx
        ev = d.buzz_events[
            (d.buzz_events.game_id == gid)
            & d.buzz_events.date.between(s.index.min(), s.index.max())
        ]
        panels.append(
            ch.line(
                names[gid],
                [ch.series("화제성 지수", range(len(s)), s.values, 1)],
                ylabel="화제성 지수",
                xlabels=[x.strftime("%m/%d") for x in s.index],
                hlines=[{"y": 100, "label": "평소"}],
                vlines=[
                    {
                        "x": int(s.index.get_indexer([r.date], method="nearest")[0]),
                        "kind": KIND[r.type],
                        "label": f"{KIND[r.type]}: {r.label}",
                        "color": cidx[r.type],
                    }
                    for r in ev.itertuples()
                ],
            )
        )
    res.attach_to("timeline.png", *panels)
    res.attach_to(
        "cause_halflife.png",
        ch.bars(
            f"급상승 {len(sg)}건의 원인",
            [{"label": KIND[k], "value": v} for k, v in share.items()],
            unit="%",
            vmax=100,
        ),
        ch.bars(
            "화제성이 절반으로 식는 데 걸린 기간(중앙값)",
            [{"label": KIND[k], "value": v, "color": cidx[k]} for k, v in hl.items()],
            unit="일",
        ),
    )
    write_summary(res, out_root)
    return res
