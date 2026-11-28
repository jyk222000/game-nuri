"""분석 노트북 공통 준비 코드.

노트북 앞부분이 길어지지 않도록 한글 폰트, 경로, 가격 이력 읽기, 일별 최저가·할인 구간 계산을 모았다.
할인 구간 기준은 서비스(backend/app/services/timing.py)와 같다: 할인율 10% 이상인 날이 이어진 구간 = 할인 1회.

노트북은 analysis/notebooks 폴더에서 열어야 `from _common import ...`가 된다 (VS Code 기본 동작).
"""

import os
import platform
from pathlib import Path
from urllib.parse import quote_plus

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# ---- 서비스(timing.py)와 같은 기준 ----
SALE_MIN_PCT = 10      # 할인율 10% 이상인 날이 이어진 구간 = 할인 1회
WINDOW_DAYS = 730      # 할인 횟수·주기 계산 기간 (최근 2년)
MIN_HISTORY_DAYS = 3   # 이력 일수가 이보다 적으면 제외

# 레포 루트와 데이터 폴더 (노트북을 어디서 열어도 같은 경로)
ROOT = Path(__file__).resolve()
while ROOT != ROOT.parent and not (ROOT / "analysis").is_dir():
    ROOT = ROOT.parent
DATA = ROOT / "analysis" / "data"

# 가격 이력은 DB(Replica)에서 SELECT로만 읽고, 한 번 읽으면 CSV로 저장해 다음부터 재사용한다.
# (발표 현장에서 VM·SSH 터널이 안 돼도 시연할 수 있다. analysis/data/ 는 Git에 올라가지 않는다.)
PRICE_CSV = Path(os.environ.get("GAMENURI_PRICE_CSV", DATA / "cache" / "price_history_pc_new.csv"))


def setup_plot() -> None:
    """한글 폰트와 발표용으로 조금 크게 잡은 글자 크기."""
    if platform.system() == "Windows":
        plt.rc("font", family="Malgun Gothic")
    elif platform.system() == "Darwin":
        plt.rc("font", family="AppleGothic")
    plt.rc("axes", unicode_minus=False, titlesize=13, labelsize=11)
    plt.rc("font", size=11)
    pd.set_option("display.max_columns", 30)
    pd.set_option("display.width", 160)


def load_price_history(game_ids, refresh: bool = False) -> pd.DataFrame:
    """PC·새 상품(item_condition='new') 가격 이력. 컬럼: game_id, store, edition, price_krw, regular_krw, discount_pct, collected_at"""
    if PRICE_CSV.exists() and not refresh:
        df = pd.read_csv(PRICE_CSV, parse_dates=["collected_at"])
    else:
        from gamenuri_common.config import Settings
        from sqlalchemy import bindparam, create_engine, text

        s = Settings(_env_file=ROOT / ".env")  # 비밀번호는 출력하지 않는다
        url = (f"mysql+pymysql://{s.mariadb_user}:{quote_plus(s.mariadb_password)}"
               f"@{s.mariadb_read_host}:{s.mariadb_port}/{s.mariadb_db}")
        query = text(
            "SELECT game_id, store, edition, price_krw, regular_krw, discount_pct, collected_at "
            "FROM price_history WHERE platform = 'PC' AND item_condition = 'new' AND game_id IN :ids"
        ).bindparams(bindparam("ids", expanding=True))
        with create_engine(url).connect() as conn:  # 읽기 전용 계정, SELECT만 실행
            df = pd.read_sql(query, conn, params={"ids": [int(i) for i in game_ids]})
        PRICE_CSV.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(PRICE_CSV, index=False)
    return df[df.game_id.isin(game_ids)].copy()


def daily_series(g: pd.DataFrame) -> pd.DataFrame:
    """게임 1개의 일별 최저가 (컬럼: day, price_krw, discount_pct).

    price_history에는 가격이 바뀐 스토어의 행만 있다. 그래서 스토어(+에디션)별 마지막 가격을 이어 채운 뒤
    그날의 최저가 한 줄만 남긴다. 이렇게 해야 모든 스토어의 '그 시점 가격'이 된다.
    """
    g = g.assign(day=g.collected_at.dt.normalize(), discount_pct=g.discount_pct.fillna(0))
    last = g.sort_values("collected_at").groupby(["day", "store", "edition"]).tail(1)
    price = last.pivot(index="day", columns=["store", "edition"], values="price_krw")
    disc = last.pivot(index="day", columns=["store", "edition"], values="discount_pct")
    price = price.sort_index().sort_index(axis=1).ffill()
    disc = disc.reindex_like(price).ffill()
    best = np.nanargmin(price.to_numpy(), axis=1)
    rows = np.arange(len(best))
    return pd.DataFrame({
        "day": price.index,
        "price_krw": price.to_numpy()[rows, best],
        "discount_pct": disc.to_numpy()[rows, best],
    })


def sale_events(d: pd.DataFrame) -> pd.DataFrame:
    """할인율이 SALE_MIN_PCT 이상인 날이 이어진 구간마다 한 건 (컬럼: start, max_pct)."""
    events, start, top = [], None, 0
    for day, pct in zip(d.day, d.discount_pct):
        if pct >= SALE_MIN_PCT:
            if start is None:
                start, top = day, pct
            else:
                top = max(top, pct)
        elif start is not None:
            events.append((start, top))
            start = None
    if start is not None:
        events.append((start, top))
    return pd.DataFrame(events, columns=["start", "max_pct"]).astype({"start": "datetime64[ns]"})


def verdict(p: float, alpha: float = 0.05) -> str:
    return "채택 (유의)" if p < alpha else "기각 못 함 (유의하지 않음)"
