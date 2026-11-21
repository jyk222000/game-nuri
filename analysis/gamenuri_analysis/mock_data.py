"""가설을 담은 목(mock) 데이터 생성기.

실제 수집 데이터가 쌓이기 전에 분석 코드·그래프·화면을 끝까지 돌려 보기 위한 가짜 데이터다.
"이런 현상이 보일 것"이라는 가설(Notion '분석 방향')을 일부러 심어 두었으므로,
여기서 나온 결과 숫자를 실제 사실처럼 발표하면 안 된다.
실데이터 로더(loader.py)로 바꾸면 같은 코드가 돈다.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .dataset import Dataset

NOW = pd.Timestamp("2026-11-21")
SEED = 2026
PC_STORES = ["steam", "epic", "gog", "humble", "fanatical", "gmg", "gamesplanet", "microsoft"]
STORE_FACTOR = {
    "steam": 1.0,
    "epic": 0.92,
    "gog": 1.05,
    "humble": 0.95,
    "fanatical": 1.12,
    "gmg": 1.0,
    "gamesplanet": 0.9,
    "microsoft": 0.8,
    "danawa": 0.7,
}
STORE_LEAD_MONTHS = {"gog": 1.8, "fanatical": 2.4, "epic": 0.6}
CATEGORIES = ["price", "optimization", "server", "translation", "content", "bug"]

# (game_id, 이름, 장르, 제작사, 출시일, 평론, 긍정률, 초기긍정률, 클리어h, 정가,
#  사양등급, 플랫폼, 동접, 유형)
# 유형: value(할인 때 만족↑) / multi(멀티플레이) / normal
_REAL = [
    (
        119133,
        "엘든 링",
        "액션",
        "FromSoftware",
        "2022-02-25",
        96,
        92,
        88,
        60,
        64800,
        3,
        "pc,ps,xbox",
        412000,
        "normal",
    ),
    (
        1877,
        "사이버펑크 2077",
        "RPG",
        "CD Projekt",
        "2020-12-10",
        86,
        86,
        52,
        26,
        66000,
        4,
        "pc,ps,xbox",
        98000,
        "value",
    ),
    (
        119171,
        "발더스 게이트 3",
        "RPG",
        "Larian",
        "2023-08-03",
        96,
        96,
        94,
        75,
        66000,
        3,
        "pc,ps",
        213000,
        "normal",
    ),
    (
        7346,
        "젤다의 전설: 티어스 오브 더 킹덤",
        "어드벤처",
        "Nintendo",
        "2023-05-12",
        96,
        95,
        94,
        60,
        79800,
        None,
        "switch",
        0,
        "normal",
    ),
    (
        113112,
        "하데스",
        "로그라이크",
        "Supergiant",
        "2020-09-17",
        93,
        98,
        97,
        22,
        28000,
        1,
        "pc,switch,ps,xbox",
        15000,
        "normal",
    ),
    (
        17000,
        "스타듀 밸리",
        "시뮬레이션",
        "ConcernedApe",
        "2016-02-26",
        86,
        98,
        97,
        55,
        16000,
        1,
        "pc,switch,ps,xbox",
        62000,
        "normal",
    ),
    (
        14593,
        "할로우 나이트",
        "어드벤처",
        "Team Cherry",
        "2017-02-24",
        87,
        97,
        96,
        28,
        18000,
        1,
        "pc,switch,ps,xbox",
        9000,
        "normal",
    ),
    (
        11426,
        "세키로: 섀도우 다이 트와이스",
        "액션",
        "FromSoftware",
        "2019-03-22",
        90,
        94,
        92,
        31,
        65800,
        2,
        "pc,ps,xbox",
        11000,
        "normal",
    ),
    (
        26192,
        "갓 오브 워",
        "액션",
        "Sony",
        "2022-01-14",
        94,
        96,
        93,
        20,
        59800,
        3,
        "pc,ps",
        21000,
        "normal",
    ),
    (
        25076,
        "레드 데드 리뎀션 2",
        "액션",
        "Rockstar",
        "2019-12-05",
        97,
        90,
        86,
        50,
        66000,
        4,
        "pc,ps,xbox",
        54000,
        "normal",
    ),
    (
        3277,
        "데이브 더 다이버",
        "시뮬레이션",
        "Mintrocket",
        "2023-06-28",
        87,
        97,
        96,
        20,
        24000,
        1,
        "pc,switch,ps",
        7000,
        "normal",
    ),
    (
        135400,
        "팰월드",
        "시뮬레이션",
        "Pocketpair",
        "2024-01-19",
        70,
        84,
        75,
        40,
        29800,
        2,
        "pc,xbox",
        38000,
        "value",
    ),
    (
        150080,
        "헬다이버즈 2",
        "슈터",
        "Arrowhead",
        "2024-02-08",
        82,
        82,
        78,
        30,
        49000,
        3,
        "pc,ps",
        61000,
        "multi",
    ),
    (
        9630,
        "포켓몬스터 스칼렛",
        "RPG",
        "Nintendo",
        "2022-11-18",
        82,
        70,
        58,
        35,
        69800,
        None,
        "switch",
        0,
        "normal",
    ),
]
# 불만 프로파일(가격, 최적화, 서버, 번역, 콘텐츠, 버그) 합 100. 패치로 줄어드는 게임은 _PATCHED
_PROFILE = {
    1877: [10, 22, 2, 4, 6, 56],
    119133: [6, 52, 8, 2, 8, 24],
    119171: [8, 20, 4, 6, 12, 50],
    135400: [14, 14, 22, 18, 24, 8],
    150080: [8, 10, 48, 6, 10, 18],
    9630: [18, 40, 2, 3, 12, 25],
    25076: [30, 36, 2, 4, 10, 18],
    11426: [10, 16, 2, 40, 6, 26],
}
_PATCHED = {1877, 119171, 150080, 135400}
_CONSOLE_FIRST = {26192: ("2018-04-20", "2022-01-14"), 9630: (None, None)}  # (콘솔, PC)
_PUB_STYLE = {  # 제작사별 장르 취향, 첫 할인 배수(1.0=평균)
    "FromSoftware": (["액션", "RPG"], 1.7),
    "CD Projekt": (["RPG"], 0.9),
    "Larian": (["RPG", "전략"], 2.0),
    "Nintendo": (["어드벤처", "액션", "시뮬레이션"], None),
    "Sony": (["액션", "어드벤처", "슈터"], 2.5),
    "Supergiant": (["로그라이크", "액션"], 0.7),
    "Rockstar": (["액션", "어드벤처"], 1.9),
    "Pocketpair": (["시뮬레이션", "슈터"], 0.4),
}
_GENRES = ["액션", "RPG", "인디", "시뮬레이션", "슈터", "어드벤처", "로그라이크", "전략"]
_GENRE_BIAS = {
    "액션": -2,
    "RPG": -1,
    "인디": 8,
    "시뮬레이션": 6,
    "로그라이크": 5,
    "슈터": -5,
    "어드벤처": 1,
    "전략": 2,
}


def _games(rng: np.random.Generator) -> pd.DataFrame:
    rows = []
    for gid, name, genre, pub, rel, critic, pos, early, ttb, price, tier, plats, ccu, vt in _REAL:
        rows.append(
            dict(
                game_id=gid,
                name=name,
                genre=genre,
                publisher=pub,
                release_date=pd.Timestamp(rel),
                critic_score=critic,
                positive_pct=pos,
                early_positive_pct=early,
                ttb_hours=ttb,
                regular_krw=price,
                rec_tier=tier,
                platforms=plats,
                ccu=ccu,
                value_type=vt,
            )
        )
    pubs = list(_PUB_STYLE) + ["기타 스튜디오"] * 10
    for i in range(34):
        pub = pubs[i % len(pubs)]
        styles = _PUB_STYLE.get(pub, (_GENRES, 1.0))[0]
        genre = str(rng.choice(styles))
        rel = pd.Timestamp("2019-06-01") + pd.Timedelta(days=int(rng.integers(0, 2800)))
        critic = int(rng.integers(62, 97))
        pos = int(np.clip(critic + _GENRE_BIAS.get(genre, 0) + rng.normal(0, 6), 40, 99))
        indie = genre in ("인디", "로그라이크", "시뮬레이션") and rng.random() < 0.8
        price = int(
            rng.choice([13000, 18000, 24000, 29800]) if indie else rng.choice([49000, 59800, 66000])
        )
        ttb = int(np.clip(rng.lognormal(3.0, 0.6), 4, 90))
        plats = "pc" if pub != "Nintendo" else "switch"
        if pub == "Sony":
            plats = "pc,ps"
        elif pub != "Nintendo" and rng.random() < 0.5:
            plats = "pc,ps,xbox"
        rows.append(
            dict(
                game_id=900001 + i,
                name=f"샘플 게임 {i + 1:02d}",
                genre=genre,
                publisher=pub,
                release_date=rel,
                critic_score=critic,
                positive_pct=pos,
                early_positive_pct=int(np.clip(pos - rng.integers(0, 14), 30, 99)),
                ttb_hours=ttb,
                regular_krw=price,
                rec_tier=None if plats == "switch" else int(rng.integers(1, 6)),
                platforms=plats,
                ccu=0 if plats == "switch" else int(rng.lognormal(8.5, 1.2)),
                value_type=str(rng.choice(["value", "multi", "normal"], p=[0.15, 0.1, 0.75])),
            )
        )
    g = pd.DataFrame(rows)
    g["tier"] = np.where(g.regular_krw >= 49000, "aaa", "indie")
    g["online_only"] = g.value_type.eq("multi")
    g["ending_pct"] = np.clip(
        78 * np.exp(-g.ttb_hours / 38) + rng.normal(0, 5, len(g)), 3, 88
    ).round(1)
    g["console_release"] = pd.NaT
    g["pc_release"] = g.release_date
    for gid, (con, pc) in _CONSOLE_FIRST.items():
        if con:
            g.loc[g.game_id == gid, ["console_release", "pc_release"]] = [
                pd.Timestamp(con),
                pd.Timestamp(pc),
            ]
    simul = (
        g.platforms.str.contains("ps|xbox") & g.console_release.isna()
    )  # 대부분은 콘솔·PC 동시 출시
    g.loc[simul, "console_release"] = g.loc[simul, "release_date"]
    # Sony 샘플은 콘솔 독점 뒤 PC 이식(30~48개월), 그 밖에는 동시 출시
    for idx in g.index[(g.publisher == "Sony") & (g.game_id > 900000)]:
        delay = int(rng.integers(30, 49))
        g.loc[idx, "console_release"] = g.loc[idx, "release_date"]
        g.loc[idx, "pc_release"] = g.loc[idx, "release_date"] + pd.Timedelta(days=int(delay * 30.4))
    return g


def _sale_events(g: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    rows = []
    seasonal = [(6, 20, 14, 1.1), (11, 20, 13, 1.25), (12, 19, 15, 1.25), (3, 14, 8, 0.9)]
    for gm in g.itertuples():
        mult = _PUB_STYLE.get(gm.publisher, (None, 1.0))[1]
        if mult is None:  # 닌텐도: 거의 할인하지 않음
            continue
        base = (10.0 if gm.tier == "aaa" else 8.5) * mult + rng.normal(0, 1.2)
        tmax, tau = (60, 14) if gm.tier == "aaa" else (45, 8)
        stores = (PC_STORES if "pc" in gm.platforms else []) + (
            ["danawa"] if gm.platforms != "pc" else []
        )
        for store in stores:
            lead = STORE_LEAD_MONTHS.get(store, 0.0)
            first = pd.Timestamp(
                gm.pc_release if store != "danawa" else gm.release_date
            ) + pd.Timedelta(days=float(max(base - lead, 1) * 30.4))
            wins = [(first, 7, 1.0)]
            for y in range(first.year, NOW.year + 1):
                for m, d, ln, boost in seasonal:
                    wins.append((pd.Timestamp(y, m, d), ln, boost))
                if store == "epic":
                    wins.append((pd.Timestamp(y, 5, 13), 14, 1.1))
            t = first
            while t < NOW:
                t += pd.Timedelta(days=int(rng.integers(60, 131)))
                wins.append((t, int(rng.integers(5, 9)), float(rng.uniform(0.3, 0.95))))
            for start, ln, boost in wins:
                if start < first or start > NOW:
                    continue
                age = (start - gm.release_date).days / 30.4
                depth = (
                    tmax
                    * (1 - np.exp(-max(age, 0) / tau))
                    * boost
                    * STORE_FACTOR[store]
                    * rng.uniform(0.85, 1.15)
                )
                depth = int(np.clip(round(depth / 5) * 5, 10, 80))
                rows.append(
                    (gm.game_id, store, start, min(start + pd.Timedelta(days=ln), NOW), depth)
                )
    return pd.DataFrame(rows, columns=["game_id", "store", "start", "end", "discount_pct"])


def _steam_discount_days(ev: pd.DataFrame, gid: int, days: pd.DatetimeIndex) -> np.ndarray:
    out = np.zeros(len(days))
    for r in ev[(ev.game_id == gid) & (ev.store == "steam")].itertuples():
        mask = (days >= r.start) & (days < r.end)
        out[mask] = np.maximum(out[mask], r.discount_pct)
    return out


def _reviews_daily(g: pd.DataFrame, ev: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    days = pd.date_range("2024-05-01", NOW - pd.Timedelta(days=1))
    out = []
    for gm in g[g.platforms.str.contains("pc")].itertuples():
        age_y = np.clip((days - gm.release_date).days.values / 365, 0, None)
        base = (60 if gm.game_id < 900000 else 14) * np.exp(-age_y / 3) + 3
        lam = base.copy()
        for r in ev[(ev.game_id == gm.game_id) & (ev.store == "steam")].itertuples():
            lift = 0.15 if r.discount_pct < 30 else 0.5 if r.discount_pct < 50 else 1.8
            t = (days - r.start).days.values
            lam = lam * (
                1
                + np.where(
                    t >= 0,
                    lift * (1 + min(0.25 * age_y.mean(), 1.0)) * np.exp(-np.clip(t, 0, None) / 6),
                    0,
                )
            )
        disc = _steam_discount_days(ev, gm.game_id, days)
        shift = {"value": 0.09, "multi": -0.04}.get(gm.value_type, 0.0)
        p = np.clip(gm.positive_pct / 100 + np.where(disc > 0, shift, 0.0), 0.05, 0.99)
        n = rng.poisson(lam)
        out.append(
            pd.DataFrame(
                {
                    "game_id": gm.game_id,
                    "date": days,
                    "n_reviews": n,
                    "n_positive": rng.binomial(n, p),
                }
            )
        )
    return pd.concat(out, ignore_index=True)


def _ccu_hourly(g: pd.DataFrame, ev: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    ts = pd.date_range(NOW - pd.Timedelta(days=7), NOW, freq="h", inclusive="left")
    out = []
    for gm in g[g.ccu > 0].itertuples():
        disc = _steam_discount_days(ev, gm.game_id, ts)  # 시간 단위로 같은 로직
        daily = 1 + 0.25 * np.sin((ts.hour.values - 6) / 24 * 2 * np.pi)
        lift = np.where(
            (disc >= 30) & (ts >= pd.Timestamp("2026-11-20")), 0.4 * (1 + gm.game_id % 3 / 10), 0
        )
        out.append(
            pd.DataFrame(
                {
                    "game_id": gm.game_id,
                    "ts": ts,
                    "ccu": (gm.ccu * daily * (1 + lift) * rng.normal(1, 0.02, len(ts))).astype(int),
                }
            )
        )
    return pd.concat(out, ignore_index=True)


def _complaints(g: pd.DataFrame, rng: np.random.Generator) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows, deck = [], []
    for gm in g[g.platforms.str.contains("pc")].itertuples():
        if gm.game_id in _PROFILE:
            w0 = np.array(_PROFILE[gm.game_id], float)
        else:
            opt = 6 + 3 * (gm.rec_tier or 2) + rng.normal(0, 4) + (20 if rng.random() < 0.15 else 0)
            rest = rng.dirichlet(np.ones(5) * 2) * (100 - max(opt, 3))
            w0 = np.array([rest[0], max(opt, 3), rest[1], rest[2], rest[3], rest[4]])
        tau = (
            3.0
            if (gm.game_id in _PATCHED or (gm.game_id > 900000 and rng.random() < 0.6))
            else 14.0
        )
        months = int(np.clip((NOW - gm.release_date).days / 30.4, 3, 24))
        for m in range(months + 1):
            w = w0.copy()
            decay = 0.3 + 0.7 * np.exp(-m / tau)
            w[1] *= 0.25 + 0.75 * decay
            w[5] *= decay
            w[0] *= 1 + 0.06 * m
            total = int((400 if gm.game_id < 900000 else 90) * np.exp(-m / 6) + 40)
            counts = rng.multinomial(total, w / w.sum())
            rows += [(gm.game_id, m, c, int(n)) for c, n in zip(CATEGORIES, counts, strict=True)]
        opt_share = w0[1] / w0.sum()
        n = 1500
        deck += [
            (gm.game_id, "desktop", n, int(rng.binomial(n, min(opt_share, 0.9)))),
            (gm.game_id, "deck", n // 5, int(rng.binomial(n // 5, min(opt_share * 2.1, 0.95)))),
        ]
    return (
        pd.DataFrame(rows, columns=["game_id", "month", "category", "count"]),
        pd.DataFrame(deck, columns=["game_id", "device", "n_reviews", "n_opt"]),
    )


def _playtime(g: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    rows = []
    for gm in g[g.platforms.str.contains("pc")].itertuples():
        bimodal = (
            gm.value_type in ("multi", "value")
            and gm.game_id % 2 == 0
            or gm.game_id in (1877, 135400, 150080)
        )
        n = 400
        if bimodal:
            short = rng.lognormal(np.log(1.5), 0.7, n)
            long_ = rng.lognormal(np.log(gm.ttb_hours * 1.1), 0.6, n)
            h = np.where(rng.random(n) < 0.5, short, long_)
        else:
            h = rng.lognormal(np.log(gm.ttb_hours * 0.9), 0.8, n)
        rows.append(pd.DataFrame({"game_id": gm.game_id, "hours": np.clip(h, 0.1, None).round(1)}))
    return pd.concat(rows, ignore_index=True)


def _buzz(
    g: pd.DataFrame, ev: pd.DataFrame, rng: np.random.Generator
) -> tuple[pd.DataFrame, pd.DataFrame]:
    days = pd.date_range(NOW - pd.Timedelta(days=180), NOW - pd.Timedelta(days=1))
    amp = {"sale": 0.55, "update": 0.45, "dlc": 0.55}
    tau = {"sale": 5.0, "update": 17.0, "dlc": 9.0}
    labels = {"update": "업데이트", "dlc": "DLC 발표"}
    daily, events = [], []
    for gm in g[(g.ccu > 0) & (g.game_id < 900000)].itertuples():
        es = []
        for r in ev[
            (ev.game_id == gm.game_id) & (ev.store == "steam") & (ev.discount_pct >= 20)
        ].itertuples():
            if days[0] <= r.start <= days[-1]:
                es.append(
                    (r.start.normalize(), "sale", f"{r.discount_pct}% 할인", r.discount_pct / 50)
                )
        t = days[0] + pd.Timedelta(days=int(rng.integers(5, 25)))
        while t < days[-1]:
            es.append((t, "update", labels["update"], 1.0))
            t += pd.Timedelta(days=int(rng.integers(30, 55)))
        es.append(
            (days[0] + pd.Timedelta(days=int(rng.integers(40, 150))), "dlc", labels["dlc"], 1.0)
        )
        base_ccu, base_rev = max(gm.ccu, 3000), 120 + gm.ccu / 800
        lift = np.zeros(len(days))
        for d, kind, _label, scale in es:
            t_ = (days - d).days.values
            lift += np.where(
                t_ >= 0, amp[kind] * scale * np.exp(-np.clip(t_, 0, None) / tau[kind]), 0
            )
        d0 = days[0] + pd.Timedelta(days=int(rng.integers(60, 150)))  # 원인 불명 급상승 1회
        lift += np.where(
            (days - d0).days.values >= 0,
            0.4 * np.exp(-np.clip((days - d0).days.values, 0, None) / 4),
            0,
        )
        daily.append(
            pd.DataFrame(
                {
                    "game_id": gm.game_id,
                    "date": days,
                    "ccu": (base_ccu * (1 + lift) * rng.normal(1, 0.03, len(days))).astype(int),
                    "new_reviews": rng.poisson(base_rev * (1 + 1.4 * lift)),
                }
            )
        )
        events += [(gm.game_id, d, k, lab) for d, k, lab, _ in es]
    return (
        pd.concat(daily, ignore_index=True),
        pd.DataFrame(events, columns=["game_id", "date", "type", "label"]),
    )


def _perf_keywords(g: pd.DataFrame, comp: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """최근 6개월 최적화 불만 수를 성능 키워드로 나눈 값 (실제로는 ES 키워드 집계)."""
    kws = ["프레임 드랍", "끊김", "최적화", "렉", "발열", "튕김"]
    rows = []
    for gid, c in comp[comp.category == "optimization"].groupby("game_id"):
        n = int(c[c.month > c.month.max() - 6]["count"].sum())
        rows += [
            (gid, k, int(v))
            for k, v in zip(kws, rng.multinomial(n, rng.dirichlet(np.ones(6) * 2)), strict=True)
        ]
    return pd.DataFrame(rows, columns=["game_id", "keyword", "count"])


def build_mock() -> Dataset:
    rng = np.random.default_rng(SEED)
    g = _games(rng)
    ev = _sale_events(g, rng)
    comp, deck = _complaints(g, rng)
    bd, be = _buzz(g, ev, rng)
    return Dataset(
        games=g,
        sale_events=ev,
        reviews_daily=_reviews_daily(g, ev, rng),
        ccu_hourly=_ccu_hourly(g, ev, rng),
        complaints=comp,
        deck_reviews=deck,
        playtime=_playtime(g, rng),
        buzz_daily=bd,
        buzz_events=be,
        perf_keywords=_perf_keywords(g, comp, rng),
        now=NOW,
        source="mock",
    )
