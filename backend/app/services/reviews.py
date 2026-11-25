"""리뷰 목록(#26)·리뷰 요약(#27). 읽기만 한다.

- 목록: ES `reviews`(MongoDB → Monstache, Steam 리뷰)에서 읽는다. 리뷰는 Steam 앱 ID로
  저장돼 있어서 game_id → game_store_ids(store=steam) → steam_appid로 바꿔 조회한다.
- 요약: MariaDB `review_summaries`(AI 배치 결과)를 읽기만 한다. Backend에서 AI를 부르지 않는다.
  긍정률은 카드와 같은 값(ratings.positive_ratios)을 쓴다. 요약이 아직 없어도 200이다.
"""

import logging
from datetime import UTC, datetime
from typing import Literal

from elasticsearch import ApiError, TransportError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.clients.es import get_es
from app.core.errors import ApiError as ApiErr
from app.core.errors import unavailable
from app.db.models import GameStoreId, ReviewSummary
from app.schemas.reviews import ReviewItem, ReviewsOut, ReviewSummaryOut
from app.services import games, ratings

log = logging.getLogger(__name__)

INDEX = "reviews"
MAX_RESULT_WINDOW = 10_000  # ES 기본 한도: 시작 위치 + size가 이 값을 넘으면 조회할 수 없다
SORTS: dict[str, list[dict]] = {
    # 도움이 됐다는 반응(votes_up)이 많은 순. 반응이 같으면 최신순, 그래도 같으면 id순(순서 고정)
    "helpful": [{"votes_up": "desc"}, {"created_at": "desc"}, {"recommendationid": "desc"}],
    "recent": [{"created_at": "desc"}, {"recommendationid": "desc"}],
}


def steam_app_id(db: Session, game_id: int) -> int | None:
    """게임의 Steam 앱 ID. 없으면(콘솔 전용 등) None."""
    external = db.scalar(
        select(GameStoreId.external_id)
        .where(GameStoreId.game_id == game_id, GameStoreId.store == "steam")
        .order_by(GameStoreId.external_id)
    )
    return int(external) if external is not None and external.isdigit() else None


def _item(source: dict) -> ReviewItem:
    minutes = source.get("playtime_at_review")  # Steam은 분 단위로 준다
    return ReviewItem(
        review_id=str(source["recommendationid"]),
        source=source.get("source") or "steam",
        recommended=bool(source.get("voted_up")),
        text=source.get("review") or "",  # 원문 전체(자르지 않는다). 접기는 프런트가 한다
        playtime_hours=round(minutes / 60) if minutes is not None else None,
        created_at=datetime.fromtimestamp(source["created_at"], UTC),
    )


# ---------- #26 리뷰 목록 ----------
def list_reviews(
    db: Session, game_id: int, page: int, size: int, sort: Literal["helpful", "recent"]
) -> ReviewsOut:
    games.ensure_exists(db, game_id)  # 없는 게임이면 404
    app_id = steam_app_id(db, game_id)
    if app_id is None:  # Steam 리뷰가 없는 게임
        return ReviewsOut(items=[], total=0, page=page, size=size)
    offset = (page - 1) * size
    if offset + size > MAX_RESULT_WINDOW:
        raise ApiErr(422, "INVALID_REQUEST", "이 뒤 페이지는 볼 수 없어요")
    try:
        result = get_es().search(
            index=INDEX,
            from_=offset,
            size=size,
            query={"term": {"steam_appid": app_id}},
            sort=SORTS[sort],
            track_total_hits=True,
            source_includes=[
                "recommendationid",
                "source",
                "voted_up",
                "review",
                "playtime_at_review",
                "created_at",
            ],
        )
        hits = result["hits"]
        items = [_item(h["_source"]) for h in hits["hits"]]
        total = int(hits["total"]["value"])
    except (ApiError, TransportError, KeyError) as exc:
        log.warning("리뷰 조회 실패: %s", type(exc).__name__)
        raise unavailable() from exc
    return ReviewsOut(items=items, total=total, page=page, size=size)


# ---------- #27 리뷰 요약 ----------
def _split(keywords: str | None) -> list[str]:
    return [k.strip() for k in (keywords or "").split(",") if k.strip()]


def _generated_by(value: str) -> Literal["ai", "fallback"] | None:
    """ERD는 ai | fallback만 허용한다. 그 밖의 값이 들어와도 응답은 깨지지 않게 null로."""
    if value == "ai":
        return "ai"
    if value == "fallback":
        return "fallback"
    return None


def get_summary(db: Session, game_id: int) -> ReviewSummaryOut:
    games.ensure_exists(db, game_id)
    row = db.get(ReviewSummary, game_id)
    ratio = ratings.positive_ratios(db, [game_id]).get(game_id)
    if row is None:  # AI 요약이 아직 없다: 긍정률만 있을 수 있다
        return ReviewSummaryOut(
            game_id=game_id,
            positive_ratio=ratio,
            summary=None,
            pros=[],
            cons=[],
            generated_by=None,
            updated_at=None,
        )
    return ReviewSummaryOut(
        game_id=game_id,
        positive_ratio=ratio,
        summary=row.summary,
        pros=_split(row.pros_keywords),
        cons=_split(row.cons_keywords),
        generated_by=_generated_by(row.generated_by),
        updated_at=row.updated_at,
    )
