"""웹 화면이 직접 그릴 차트 명세(JSON). 계산은 파이썬이 끝내고, 화면은 이 값을 그리기만 한다.

색은 1~8 번호로 지정하며 style.PALETTE 와 프론트 --c1~--c8 이 같은 색이다.
같은 변수로 matplotlib 그림(PNG)도 만들기 때문에 두 결과가 어긋나지 않는다.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from typing import Any


def _n(v: Any, d: int = 2) -> Any:
    """숫자는 반올림하고 NaN/inf 는 None 으로 (JSON 에 NaN 이 들어가면 안 된다)."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return v
    return None if math.isnan(f) or math.isinf(f) else round(f, d)


def _list(xs: Iterable[Any], d: int = 2) -> list[Any]:
    return [_n(x, d) for x in xs]


def series(name: str, x: Iterable[Any], y: Iterable[Any], color: int = 1) -> dict[str, Any]:
    return {"name": name, "color": color, "x": _list(x), "y": _list(y)}


def line(
    title: str,
    ser: Sequence[dict[str, Any]],
    *,
    xlabel: str = "",
    ylabel: str = "",
    yunit: str = "",
    xunit: str = "",
    xlabels: Sequence[str] | None = None,
    vlines: Sequence[dict[str, Any]] = (),
    hlines: Sequence[dict[str, Any]] = (),
    ymin: float | None = None,
    zero: bool = False,
) -> dict[str, Any]:
    """선 그래프.

    xlabels 가 있으면 x 는 0부터의 위치이고 눈금 글자는 xlabels 에서 가져온다(날짜 등).
    vlines: {x,label,kind?,color?}, hlines: {y,label}
    """
    return {
        "type": "line",
        "title": title,
        "series": list(ser),
        "xlabel": xlabel,
        "ylabel": ylabel,
        "yunit": yunit,
        "xunit": xunit,
        "xlabels": list(xlabels) if xlabels else None,
        "ymin": ymin,
        "zero": zero,
        "vlines": [{**v, "x": _n(v["x"])} for v in vlines],
        "hlines": [{**h, "y": _n(h["y"])} for h in hlines],
    }


def scatter(
    title: str,
    points: Sequence[dict[str, Any]],
    *,
    groups: Sequence[dict[str, Any]] = (),
    xlabel: str = "",
    ylabel: str = "",
    xlim: tuple[float, float] | None = None,
    ylim: tuple[float, float] | None = None,
    xunit: str = "",
    yunit: str = "",
    xticks: Sequence[dict[str, Any]] = (),
    diagonal: bool = False,
    hline: dict[str, Any] | None = None,
    curve: Sequence[tuple[float, float]] = (),
    curve_label: str = "",
) -> dict[str, Any]:
    """점 그래프. points: {x,y,group?,label?}, groups: [{name,color}].

    이름(label)이 있는 점은 크게 그리고 글자를 붙인다.
    """
    return {
        "type": "scatter",
        "title": title,
        "groups": list(groups),
        "xlabel": xlabel,
        "ylabel": ylabel,
        "xlim": xlim,
        "ylim": ylim,
        "xunit": xunit,
        "yunit": yunit,
        "xticks": list(xticks),
        "diagonal": diagonal,
        "hline": hline,
        "curve": [[_n(a), _n(b)] for a, b in curve],
        "curve_label": curve_label,
        "points": [{**p, "x": _n(p["x"]), "y": _n(p["y"])} for p in points],
    }


def bars(
    title: str,
    items: Sequence[dict[str, Any]],
    *,
    unit: str = "",
    vmax: float | None = None,
    orient: str = "h",
    color: int = 1,
    xlabel: str = "",
    mark: dict[str, Any] | None = None,
    marks: Sequence[dict[str, Any]] = (),
) -> dict[str, Any]:
    """막대. items: {label,value,color?,note?}.

    value 가 None 이면 note 글자만 보인다. orient: h(가로) | v(세로).
    """
    return {
        "type": "bars",
        "title": title,
        "unit": unit,
        "vmax": vmax,
        "orient": orient,
        "color": color,
        "xlabel": xlabel,
        "marks": list(marks) or ([mark] if mark else []),
        "items": [{**i, "value": _n(i.get("value"), 1)} for i in items],
    }


def stacked(
    title: str, keys: Sequence[dict[str, str]], rows: Sequence[dict[str, Any]], unit: str = "%"
) -> dict[str, Any]:
    """100% 누적 막대. keys: {key,label}, rows: {label, values:{key:수}}"""
    return {
        "type": "stacked",
        "title": title,
        "unit": unit,
        "keys": list(keys),
        "rows": [
            {"label": r["label"], "values": {k: _n(v, 1) for k, v in r["values"].items()}}
            for r in rows
        ],
    }


def heatmap(
    title: str,
    rows: Sequence[str],
    cols: Sequence[str],
    values: Sequence[Sequence[Any]],
    unit: str = "%",
) -> dict[str, Any]:
    return {
        "type": "heatmap",
        "title": title,
        "unit": unit,
        "rows": list(rows),
        "cols": list(cols),
        "values": [[_n(v, 1) for v in r] for r in values],
    }
