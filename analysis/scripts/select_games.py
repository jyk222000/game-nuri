#!/usr/bin/env python3
"""겜누리 수집 대상 게임 1,000건 선정기.

입력: build_pool.py 가 만든 pool.csv (게임 1행, IGDB ID 기준)
출력: games_1000.csv (선정 결과 + 배치/티어), selection_report.md (기준 충족 현황)

방식: 하드 필터로 후보를 거른 뒤, 점수 합을 최대로 하는 1,000건을
      쿼터(분석 A1~A8 최소 조건)를 만족하도록 MILP(HiGHS)로 고른다.
      쿼터는 '소프트'라서 못 채워도 해가 나오고, 부족분은 리포트에 나온다.

사용:  python analysis/scripts/select_games.py [--pool pool.csv] [--out out_dir] [--n 1000]
"""

from __future__ import annotations

import argparse
import math
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import lil_matrix

DATA = Path(__file__).resolve().parents[1] / "data" / "game_pool"

CONSOLES = {"PS5", "PS4", "Switch", "Switch2", "XboxSeries", "XboxOne"}
ALLOWED_TYPES = {0, 8, 9, 10}  # IGDB game_type: 본편, 리메이크, 리마스터, 확장판 본편
MIN_AGE_DAYS = 180  # 출시 후 최소 경과일 (가격 이력 확보)
MIN_KO_REVIEWS = 200  # A4 키워드 추출·⑤ 요약 최소 한국어 리뷰 수 (build_pool.py 와 같게)
MIN_HISTORY_MONTHS = 6  # 유료 게임 가격 이력 최소 길이
PUBLISHER_CAP = 40  # 한 회사가 차지할 수 있는 최대 게임 수
SERIES_MIN_MEMBERS = 3
SERIES_MAX_MEMBERS = 12
PENALTY = 3.0  # 쿼터 1건 부족당 벌점 (게임 점수는 0~1)

BOOL_COLS = ["is_free", "is_online", "is_adult", "has_kr_price"]
NUM_COLS = [
    "review_count_ko",
    "positive_pct_ko",
    "rating_count",
    "aggregated_rating",
    "aggregated_rating_count",
    "ccu_peak",
    "discount_events_24m",
    "history_months",
    "ttb_normally_sec",
    "ttb_count",
    "game_type",
]


def load_pool(path: Path) -> pd.DataFrame:
    df = pd.read_csv(
        path, dtype={"steam_appid": "string", "itad_id": "string", "series_id": "string"}
    )
    for c in BOOL_COLS:
        df[c] = df[c].fillna(False).astype(str).str.lower().isin(["true", "1", "yes"])
    for c in NUM_COLS:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    for c in ["release_date", "pc_release_date", "console_first_release_date"]:
        df[c] = pd.to_datetime(df[c], errors="coerce")
    df["plat_set"] = df["platforms"].fillna("").map(lambda s: {p for p in s.split("|") if p})
    df["genre_primary"] = df["genres"].fillna("").map(lambda s: s.split("|")[0] if s else "")
    # A2 네이버 데이터랩 검색어: 한글 이름이 2글자 이하면 일반어와 섞여 추이가 오염된다
    df["kw_ambiguous"] = df["name_ko"].notna() & (
        df["name_ko"].fillna("").str.replace(r"\s", "", regex=True).str.len() <= 2
    )
    df["n_console"] = df["plat_set"].map(lambda s: len(s & CONSOLES))
    df["has_pc"] = df["plat_set"].map(lambda s: "PC" in s)
    return df


def hard_filter(df: pd.DataFrame, today: date) -> tuple[pd.DataFrame, dict]:
    """반환: (통과 후보, 탈락 사유별 건수). 한 게임이 여러 사유면 첫 사유로 센다."""
    t = pd.Timestamp(today)
    rules = [
        ("H1 본편 아님(DLC·번들 등)", ~df["game_type"].isin(ALLOWED_TYPES)),
        (
            "H2 Steam appid/ITAD id 없음(ID 통합 불가)",
            df["steam_appid"].isna() | df["itad_id"].isna(),
        ),
        (
            "H3 미출시·출시 180일 미만",
            df["release_date"].isna() | ((t - df["release_date"]).dt.days < MIN_AGE_DAYS),
        ),
        (
            f"H4 한국어 리뷰 {MIN_KO_REVIEWS}건 미만",
            df["review_count_ko"].fillna(0) < MIN_KO_REVIEWS,
        ),
        ("H5 성인 전용", df["is_adult"]),
        ("H6 한국 판매가 없음(판매 중단 등)", ~df["has_kr_price"] & ~df["is_free"]),
        (
            "H7 유료인데 가격 이력 6개월 미만",
            ~df["is_free"] & (df["history_months"].fillna(0) < MIN_HISTORY_MONTHS),
        ),
    ]
    reasons: dict[str, int] = {}
    keep = pd.Series(True, index=df.index)
    for name, bad in rules:
        hit = keep & bad
        reasons[name] = int(hit.sum())
        keep &= ~bad
    return df[keep].copy(), reasons


def pct_rank(s: pd.Series) -> pd.Series:
    return s.fillna(0).rank(pct=True)


def add_score(df: pd.DataFrame) -> pd.DataFrame:
    df["score"] = (
        0.35 * pct_rank(np.log1p(df["review_count_ko"]))
        + 0.20 * pct_rank(np.log1p(df["rating_count"]))
        + 0.15 * pct_rank(np.log1p(df["ccu_peak"]))
        + 0.15 * (df["n_console"].clip(upper=3) / 3)
        + 0.15 * pct_rank(df["discount_events_24m"])
    )
    return df


def quota_defs(df: pd.DataFrame, n: int, today: date) -> list[dict]:
    """(이름, 대상 분석, 조건 마스크, 최소, 최대). 비율은 n에 맞춰 환산."""
    s = n / 1000
    paid = ~df["is_free"]
    q = [
        ("Q1 PC+콘솔 동시 보유", "A8·A6·①", df["has_pc"] & (df["n_console"] >= 1), 450 * s, None),
        (
            "Q2 평론 점수 있음(5건↑)",
            "A3",
            df["aggregated_rating_count"].fillna(0) >= 5,
            500 * s,
            None,
        ),
        ("Q3 한국어 긍정률 75% 미만", "A4", df["positive_pct_ko"] < 75, 150 * s, None),
        (
            "Q4 클리어 시간 있음(3명↑)",
            "A7·④",
            (df["ttb_normally_sec"] > 0) & (df["ttb_count"].fillna(0) >= 3),
            550 * s,
            None,
        ),
        ("Q6 출시 2018년 이전", "A1·A5", df["release_date"].dt.year < 2018, 150 * s, None),
        ("Q7 온라인 게임", "⑦·A2", df["is_online"], 200 * s, None),
        (
            "Q8 온라인+동접 500 미만(경고 시연)",
            "⑦",
            df["is_online"] & (df["ccu_peak"].fillna(0) < 500),
            40 * s,
            None,
        ),
        ("Q9 무료 게임 상한", "–", df["is_free"], None, 80 * s),
        (
            "Q10 한글 검색어 확보(3글자↑)",
            "A2·다나와 매칭",
            df["name_ko"].notna() & ~df["kw_ambiguous"],
            600 * s,
            None,
        ),
        (
            "Q11 할인 이력 3회↑(유료)",
            "A1",
            paid & (df["discount_events_24m"].fillna(0) >= 3),
            600 * s,
            None,
        ),
        (
            "Q12 할인 이력 0회(유료)",
            "A6",
            paid & (df["discount_events_24m"].fillna(0) == 0),
            40 * s,
            None,
        ),
    ]
    out = [dict(name=a, use=b, mask=m.to_numpy(), lo=lo, hi=hi) for a, b, m, lo, hi in q]
    # 장르: 후보 수 상위 8개는 각 60건 이상, 어느 장르도 300건 초과 금지
    top_genres = df["genre_primary"].value_counts().head(8).index
    for g in top_genres:
        out.append(
            dict(
                name=f"Q13 장르 {g}",
                use="A7",
                mask=(df["genre_primary"] == g).to_numpy(),
                lo=60 * s,
                hi=300 * s,
            )
        )
    # 출시 연도: 한 해가 20% 초과 금지 (시계열 쏠림 방지)
    for y, cnt in df["release_date"].dt.year.value_counts().items():
        if cnt > 200 * s:
            out.append(
                dict(
                    name=f"Q14 출시 {int(y)}년 상한",
                    use="A1·A5",
                    mask=(df["release_date"].dt.year == y).to_numpy(),
                    lo=None,
                    hi=200 * s,
                )
            )
    return out


def solve(
    df: pd.DataFrame, n: int, today: date, time_limit: int, target_n: int | None = None, log=print
):
    """n = 실제로 고를 건수, target_n = 쿼터 목표를 환산하는 기준 건수(기본 n).
    후보가 모자라 n < target_n 이면 쿼터를 1,000건 기준 그대로 두고 부족분을 리포트에 드러낸다."""
    target_n = target_n or n
    N = len(df)
    quotas = quota_defs(df, target_n, today)
    score = df["score"].to_numpy()

    # 시리즈(A5): 후보 중 3~12편인 시리즈는 '통째로' 넣거나 통째로 뺀다.
    # 주의: groupby(...).indices 는 그 DataFrame 기준 위치를 돌려준다. 값이 비어 있는 행을 먼저
    # 걸러낸 DataFrame 에 쓰면 위치가 df 와 어긋나므로, df 전체에 groupby 한다(NaN 키는 자동 제외).
    ser = {
        k: v
        for k, v in df.groupby("series_id").indices.items()
        if SERIES_MIN_MEMBERS <= len(v) <= SERIES_MAX_MEMBERS
    }
    # 제작사(A6): 6편 이상 후보가 있는 회사
    pub = df.groupby("publisher").indices
    pub_all = {k: v for k, v in pub.items() if len(v) > PUBLISHER_CAP}
    pub6 = {k: v for k, v in pub.items() if len(v) >= 6}

    S, P = len(ser), len(pub6)
    soft = list(quotas)  # 각 쿼터마다 슬랙 1개
    n_slack = len(soft) + 2  # + 시리즈 수, 제작사 수
    nv = N + S + P + n_slack
    iy_s, iy_p, i_sl = N, N + S, N + S + P

    lo_b, hi_b = [], []
    A = lil_matrix((2 + 2 * len(soft) + S + P + len(pub_all) + 4, nv))
    r = 0

    def add(lo, hi):
        nonlocal r
        lo_b.append(lo)
        hi_b.append(hi)
        r += 1

    # 합계 = n
    A[r, :N] = 1
    add(n, n)
    # 쿼터 (소프트)
    for k, q in enumerate(soft):
        m = q["mask"].astype(float)
        A[r, :N] = m
        if q["lo"] is not None and q["hi"] is None:
            A[r, i_sl + k] = 1
            add(q["lo"], np.inf)
        elif q["hi"] is not None and q["lo"] is None:
            A[r, i_sl + k] = -1
            add(-np.inf, q["hi"])
        else:  # 구간: 아래쪽만 소프트, 위쪽은 하드 (별도 행)
            A[r, i_sl + k] = 1
            add(q["lo"], np.inf)
            A[r, :N] = m
            add(-np.inf, q["hi"])
    # 시리즈 수 ≥ 40·s, 6편↑ 제작사 수 ≥ 25·s (소프트: 마지막 두 슬랙)
    k_ser, k_pub = len(soft), len(soft) + 1
    for j, (_, idx) in enumerate(ser.items()):
        A[r, idx] = 1
        A[r, iy_s + j] = -len(idx)
        add(0, np.inf)  # y=1 이면 그 시리즈 전부 포함
    A[r, iy_s : iy_s + S] = 1
    A[r, i_sl + k_ser] = 1
    add(40 * target_n / 1000, np.inf)
    for j, (_, idx) in enumerate(pub6.items()):
        A[r, idx] = 1
        A[r, iy_p + j] = -6
        add(0, np.inf)  # y=1 이면 6편 이상
    A[r, iy_p : iy_p + P] = 1
    A[r, i_sl + k_pub] = 1
    add(25 * target_n / 1000, np.inf)
    for _, idx in pub_all.items():  # 한 회사 상한
        A[r, idx] = 1
        add(-np.inf, PUBLISHER_CAP * target_n / 1000)
    A = A[:r].tocsr()

    c = np.zeros(nv)
    c[:N] = -score
    c[i_sl:] = PENALTY
    integrality = np.zeros(nv)
    integrality[: N + S + P] = 1
    lb = np.zeros(nv)
    ub = np.ones(nv)
    ub[i_sl:] = np.inf
    log(f"MILP: 변수 {nv}, 제약 {r} (후보 {N}, 시리즈 {S}, 제작사 {P})")
    res = milp(
        c,
        constraints=LinearConstraint(A, lo_b, hi_b),
        integrality=integrality,
        bounds=Bounds(lb, ub),
        options={"time_limit": time_limit, "mip_rel_gap": 0.005},
    )
    if res.x is None:
        raise SystemExit(f"해를 찾지 못함: {res.message}")
    x = np.round(res.x[:N]).astype(bool)
    info = dict(
        status=res.message,
        gap=getattr(res, "mip_gap", None),
        n_series=int(round(res.x[iy_s : iy_s + S].sum())),
        n_pub=int(round(res.x[iy_p : iy_p + P].sum())),
    )
    return x, quotas, info


def report(df_all, df_cand, sel, quotas, rej, info, n, out: Path) -> str:
    """n = 목표 건수(쿼터 환산 기준). 실제 선정 건수는 len(sel)."""
    sel = sel.copy()
    lines = [f"# 선정 리포트 ({date.today()})", ""]
    if len(sel) < n:
        lines += [
            f"> ⚠️ **목표 {n}건 중 {len(sel)}건만 선정(부족 {n - len(sel)}건).** "
            f"하드 필터 통과 후보가 "
            f"{len(df_cand)}건뿐이라 후보를 전부 넣었다. 쿼터 목표는 {n}건 기준 그대로 둬서 "
            f"부족분이 드러난다. 풀을 늘리거나 필터 기준을 팀과 조정해야 한다.",
            "",
        ]
    lines += [
        f"- 입력 {len(df_all)}건 → 하드 필터 통과 {len(df_cand)}건 → 선정 {len(sel)}건",
        f"- 솔버: {info['status']} (gap {info['gap']})",
        "",
        "## 하드 필터 탈락",
        "",
    ]
    lines += [f"- {k}: {v}건" for k, v in rej.items()] + [
        "",
        "## 쿼터 충족 현황",
        "",
        "| 쿼터 | 분석 | 목표 | 전체 | 상위100 | 상위300 | 결과 |",
        "|---|---|---|---|---|---|---|",
    ]
    idx = {g: i for i, g in enumerate(df_cand["game_id"])}
    for q in quotas:
        m = q["mask"]

        def cnt(sub, m=m):
            return int(sum(m[idx[g]] for g in sub["game_id"]))

        tot = cnt(sel)
        lo, hi = q["lo"], q["hi"]
        goal = (f"≥{lo:.0f}" if lo is not None else "") + (f" ≤{hi:.0f}" if hi is not None else "")
        ok = (lo is None or tot >= lo - 1e-6) and (hi is None or tot <= hi + 1e-6)
        lines.append(
            f"| {q['name']} | {q['use']} | {goal.strip()} | {tot} | "
            f"{cnt(sel[sel['rank'] <= 100])} | {cnt(sel[sel['rank'] <= 300])} | "
            f"{'✅' if ok else '⚠️ 부족'} |"
        )
    lines += [
        "",
        f"- 포함된 시리즈 {info['n_series']}개(목표 ≥{40 * n // 1000}), "
        f"6편↑ 제작사 {info['n_pub']}곳(목표 ≥{25 * n // 1000})",
    ]
    top = sel[sel["rank"] <= 300]
    cons = int((top["n_console"] >= 1).sum())
    all_cons = int((sel["n_console"] >= 1).sum())
    kw_ok = int((sel["name_ko"].notna() & ~sel["kw_ambiguous"]).sum())
    lines += [
        "",
        "## 다나와 부하 추정 (게임당 요청 ≈4건 × 10초, robots.txt Crawl-delay)",
        "",
        f"- 상위 300 중 콘솔 보유 {cons}건 → 6시간 주기 1회 ≈ {cons * 4 * 10 / 3600:.1f}시간",
        f"- 선정 전체 중 콘솔 보유 {all_cons}건 → 1회 ≈ {all_cons * 4 * 10 / 3600:.1f}시간 "
        f"(6시간 초과면 하위 배치는 일 1회로)",
        "",
        "## 네이버 데이터랩 호출 추정 (A2)",
        "",
        f"- 검색어 확보 {kw_ok}건, "
        f"모호한 이름 {int(sel['kw_ambiguous'].sum())}건(별칭·제외어 필요)",
        f"- 비율이 요청마다 따로 100 기준이라 요청마다 기준 검색어 1개를 넣어야 함 → "
        f"요청당 4게임, 기간 1개당 약 {math.ceil(kw_ok / 4)}회",
        "",
        "## 리뷰 수집 부하 추정",
        "",
        f"- 게임당 최대 1,500건 = 15페이지 × 약 3초 → {len(sel) * 15 * 3 / 3600:.1f}시간(최초 1회)",
        f"- 원본 약 {len(sel) * 1500 * 830 / 1e9:.1f}GB (리뷰당 830B 기준)",
    ]
    text = "\n".join(lines) + "\n"
    (out / "selection_report.md").write_text(text, encoding="utf-8")
    return text


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # Windows 콘솔(cp949)에서 이모지·한글 출력 오류 방지
    ap = argparse.ArgumentParser()
    ap.add_argument("--pool", type=Path, default=DATA / "pool.csv")
    ap.add_argument("--out", type=Path, default=DATA / "result")
    ap.add_argument("--n", type=int, default=1000)
    ap.add_argument("--today", type=date.fromisoformat, default=date.today())
    ap.add_argument("--time-limit", type=int, default=120)
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)

    df_all = load_pool(a.pool)
    cand, rej = hard_filter(df_all, a.today)
    cand = add_score(cand).reset_index(drop=True)
    print(f"후보 {len(df_all)} → 필터 통과 {len(cand)}")
    n_pick = min(a.n, len(cand))
    if n_pick < a.n:
        print(f"⚠️ 후보 {len(cand)}건이 목표 {a.n}건보다 적음 → {n_pick}건만 선정한다 (후보 전부)")
    x, quotas, info = solve(cand, n_pick, a.today, a.time_limit, target_n=a.n)
    sel = cand[x].sort_values("score", ascending=False).copy()
    sel["rank"] = range(1, len(sel) + 1)
    sel["batch"] = np.where(sel["rank"] <= 100, 1, np.where(sel["rank"] <= 300, 2, 3))
    sel["tier"] = np.where(sel["rank"] <= 300, "A(전체 수집)", "B(축소 수집)")
    cols = [
        "rank",
        "batch",
        "tier",
        "game_id",
        "name",
        "name_ko",
        "steam_appid",
        "itad_id",
        "release_date",
        "kw_ambiguous",
        "platforms",
        "genres",
        "publisher",
        "series_name",
        "review_count_ko",
        "positive_pct_ko",
        "aggregated_rating",
        "discount_events_24m",
        "is_free",
        "is_online",
        "score",
    ]
    sel[cols].to_csv(a.out / "games_1000.csv", index=False, encoding="utf-8-sig")
    print(report(df_all, cand, sel, quotas, rej, info, a.n, a.out))


if __name__ == "__main__":
    main()
