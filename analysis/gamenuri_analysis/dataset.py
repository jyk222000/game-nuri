from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class Dataset:
    """분석 입력 묶음. 컬럼은 docs/contracts/erd.sql 의 정제 테이블을 가정한 형태다.

    games         game_id, name, genre, tier(aaa|indie), publisher, release_date, critic_score,
                  positive_pct, early_positive_pct, ttb_hours, ending_pct, rec_tier(1~5|NaN),
                  regular_krw, online_only, value_type, platforms, console_release, pc_release, ccu
    sale_events   game_id, store, start, end, discount_pct
    reviews_daily game_id, date, n_reviews, n_positive
    ccu_hourly    game_id, ts, ccu
    complaints    game_id, month(출시 후 개월), category, count   (부정 리뷰 키워드 유형별)
    deck_reviews  game_id, device(desktop|deck), n_reviews, n_opt
    playtime      game_id, hours (리뷰어 플레이 시간 표본)
    buzz_daily    game_id, date, ccu, new_reviews
    buzz_events   game_id, date, type(sale|update|dlc), label
    perf_keywords game_id, keyword, count   (최근 6개월 성능 관련 키워드 언급 수, ES 집계)
    """

    games: pd.DataFrame
    sale_events: pd.DataFrame
    reviews_daily: pd.DataFrame
    ccu_hourly: pd.DataFrame
    complaints: pd.DataFrame
    deck_reviews: pd.DataFrame
    playtime: pd.DataFrame
    buzz_daily: pd.DataFrame
    buzz_events: pd.DataFrame
    perf_keywords: pd.DataFrame
    now: pd.Timestamp
    source: str  # "mock" | "db"

    def name_of(self, game_id: int) -> str:
        return str(self.games.loc[self.games.game_id == game_id, "name"].iloc[0])
