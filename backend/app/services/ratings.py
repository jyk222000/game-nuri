"""게임 카드의 긍정 비율(positive_ratio, 0~1). 읽기만 한다.

우선순위:
1. `game_review_stats`의 한국어 긍정률(`positive_pct_ko`): Steam 스토어 표시와 같은 값
2. 한국어 값이 없으면 전체 언어 긍정률(`positive_pct_all`)
3. 둘 다 없으면 `review_summaries.positive_ratio` (AI 요약 배치, 아직 없을 수 있다)
4. 그래도 없으면 값 없음(None)
"""

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import GameReviewStats, ReviewSummary


def positive_ratios(db: Session, game_ids: Iterable[int]) -> dict[int, float]:
    """game_id → 긍정 비율. 값이 없는 게임은 결과에 넣지 않는다."""
    ids = list(set(game_ids))
    if not ids:
        return {}
    result: dict[int, float] = {}
    for gid, pct_ko, pct_all in db.execute(
        select(
            GameReviewStats.game_id,
            GameReviewStats.positive_pct_ko,
            GameReviewStats.positive_pct_all,
        ).where(GameReviewStats.game_id.in_(ids))
    ):
        pct = pct_ko if pct_ko is not None else pct_all
        if pct is not None:
            result[gid] = pct / 100
    missing = [i for i in ids if i not in result]
    if missing:
        for gid, ratio in db.execute(
            select(ReviewSummary.game_id, ReviewSummary.positive_ratio).where(
                ReviewSummary.game_id.in_(missing), ReviewSummary.positive_ratio.is_not(None)
            )
        ):
            result[gid] = float(ratio)
    return result
