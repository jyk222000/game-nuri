"""카드의 positive_ratio: game_review_stats(한국어 → 전체 언어) → review_summaries → 없음."""

from decimal import Decimal

from app.db.models import GameReviewStats, ReviewSummary
from app.services import ratings
from sqlalchemy.orm import Session

from tests.conftest import NOW, seed


def _stats(game_id, ko=None, all_=None) -> GameReviewStats:
    return GameReviewStats(
        game_id=game_id, positive_pct_ko=ko, positive_pct_all=all_, updated_at=NOW
    )


def _summary(game_id, ratio) -> ReviewSummary:
    return ReviewSummary(
        game_id=game_id, positive_ratio=Decimal(ratio), generated_by="ai", updated_at=NOW
    )


def _ratio(client, game_id):
    items = client.get("/api/games?size=10").json()["items"]
    return next(i["positive_ratio"] for i in items if i["game_id"] == game_id)


def test_korean_percent_is_used_first(env) -> None:
    client, engine, _ = env
    with seed(engine) as s:
        s.add_all([_stats(5, ko=79, all_=90), _summary(5, "0.500")])
    assert _ratio(client, 5) == 0.79


def test_falls_back_to_all_languages_then_summary_then_none(env) -> None:
    client, engine, _ = env
    with seed(engine) as s:
        s.add_all(
            [
                _stats(5, ko=None, all_=85),  # 한국어 없음 → 전체 언어
                _stats(7),  # 둘 다 없음 → 요약 배치 값
                _summary(7, "0.640"),
            ]
        )
    assert _ratio(client, 5) == 0.85
    assert _ratio(client, 7) == 0.64
    assert _ratio(client, 119133) is None  # 아무 데이터도 없음


def test_zero_percent_is_a_value_not_missing(env) -> None:
    client, engine, _ = env
    with seed(engine) as s:
        s.add(_stats(5, ko=0))
    assert _ratio(client, 5) == 0.0


def test_positive_ratios_empty_and_batch(env) -> None:
    _, engine, _ = env
    with seed(engine) as s:
        s.add_all([_stats(5, ko=60), _stats(7, ko=100)])
    with Session(engine) as db:
        assert ratings.positive_ratios(db, []) == {}
        assert ratings.positive_ratios(db, [5, 7, 119133]) == {5: 0.6, 7: 1.0}
