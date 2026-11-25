"""#26 리뷰 목록(ES `reviews`), #27 리뷰 요약(MariaDB `review_summaries`). ES는 가짜로 확인한다.

ES 응답·문서 모양은 서버에서 확인한 실제 값(recommendationid 문자열, 분 단위 playtime_at_review,
epoch 초 created_at)과 같게 만들었다.
"""

from datetime import UTC, datetime

import pytest
from app.db.models import GameReviewStats, GameStoreId, ReviewSummary
from app.services import reviews
from elastic_transport import ConnectionError as EsConnectionError

from tests.conftest import NOW, seed

EPOCH = 1795418735  # 실제 문서의 created_at


def _doc(
    rid="240839937", voted_up=False, review="재밌어요", minutes=531, created_at=EPOCH, **extra
):  # noqa: ANN003, ANN202
    source = {
        "recommendationid": rid,
        "source": "steam",
        "voted_up": voted_up,
        "review": review,
        "created_at": created_at,
    }
    if minutes is not None:
        source["playtime_at_review"] = minutes
    source.update(extra)
    return {"_id": "x", "_source": source}


def _result(*docs: dict, total: int | None = None) -> dict:
    return {
        "hits": {
            "total": {"value": len(docs) if total is None else total, "relation": "eq"},
            "hits": list(docs),
        }
    }


class FakeEs:
    def __init__(self, result: dict | None = None, error: Exception | None = None) -> None:
        self.result, self.error = result, error
        self.calls: list[dict] = []

    def search(self, **kwargs):  # noqa: ANN003
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.result


def use_es(monkeypatch, es: FakeEs) -> FakeEs:  # noqa: ANN001
    monkeypatch.setattr(reviews, "get_es", lambda: es)
    return es


@pytest.fixture
def steam_game(env):  # noqa: ANN001
    """게임 7은 Steam 앱 1091500, 게임 5는 Steam ID 없음(콘솔 전용 같은 경우)."""
    client, engine, current = env
    with seed(engine) as s:
        s.add(GameStoreId(game_id=7, store="steam", external_id="1091500"))
    return client, engine, current


# ---------- #26 목록 ----------
def test_list_maps_es_documents_to_contract_fields(steam_game, monkeypatch) -> None:  # noqa: ANN001
    client, *_ = steam_game
    es = use_es(
        monkeypatch,
        FakeEs(_result(_doc(), _doc(rid="240767060", voted_up=True, minutes=2038), total=412)),
    )
    body = client.get("/api/games/7/reviews").json()
    first, second = body["items"]
    assert first == {
        "review_id": "240839937",
        "source": "steam",
        "recommended": False,
        "text": "재밌어요",
        "playtime_hours": 9,  # 531분 → 9시간(반올림)
        "created_at": datetime.fromtimestamp(EPOCH, UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    assert second["recommended"] is True and second["playtime_hours"] == 34  # 2038분
    assert (body["total"], body["page"], body["size"]) == (412, 1, 10)
    call = es.calls[0]
    assert call["index"] == "reviews" and call["query"] == {"term": {"steam_appid": 1091500}}
    assert call["from_"] == 0 and call["size"] == 10 and call["track_total_hits"] is True


def test_list_default_sort_is_helpful_and_recent_is_available(steam_game, monkeypatch) -> None:  # noqa: ANN001
    client, *_ = steam_game
    es = use_es(monkeypatch, FakeEs(_result()))
    client.get("/api/games/7/reviews")
    client.get("/api/games/7/reviews?sort=recent")
    assert es.calls[0]["sort"][0] == {"votes_up": "desc"}  # 기본: 도움이 된 순
    assert es.calls[1]["sort"][0] == {"created_at": "desc"}  # 최신순
    for call in es.calls:  # 순서가 매번 같도록 마지막 기준을 둔다
        assert call["sort"][-1] == {"recommendationid": "desc"}


def test_list_paging_offset(steam_game, monkeypatch) -> None:  # noqa: ANN001
    client, *_ = steam_game
    es = use_es(monkeypatch, FakeEs(_result()))
    body = client.get("/api/games/7/reviews?page=3&size=5").json()
    assert (body["page"], body["size"]) == (3, 5)
    assert es.calls[0]["from_"] == 10 and es.calls[0]["size"] == 5


def test_list_sends_full_text_and_handles_missing_playtime(steam_game, monkeypatch) -> None:  # noqa: ANN001
    client, *_ = steam_game
    long_bbcode = "[h1]제목[/h1]\n" + "다" * 8000
    use_es(
        monkeypatch,
        FakeEs(
            _result(
                _doc(review="가" * 600, minutes=None),
                _doc(rid="2", review="나" * 500),
                _doc(rid="3", review=long_bbcode),
            )
        ),
    )
    first, second, third = client.get("/api/games/7/reviews").json()["items"]
    assert first["text"] == "가" * 600 and first["playtime_hours"] is None  # 잘리지 않고 …도 없다
    assert second["text"] == "나" * 500
    assert third["text"] == long_bbcode  # 8천 자도, BBCode도 그대로


def test_list_game_without_steam_id_is_empty_and_skips_es(env, monkeypatch) -> None:  # noqa: ANN001
    client, *_ = env
    es = use_es(monkeypatch, FakeEs(_result(_doc())))
    body = client.get("/api/games/5/reviews").json()
    assert body == {"items": [], "total": 0, "page": 1, "size": 10}
    assert es.calls == []


def test_list_unknown_game_is_404(env, monkeypatch) -> None:  # noqa: ANN001
    client, *_ = env
    es = use_es(monkeypatch, FakeEs(_result()))
    r = client.get("/api/games/999999/reviews")
    assert r.status_code == 404 and r.json()["error"]["code"] == "NOT_FOUND" and es.calls == []


def test_list_es_failure_is_503(steam_game, monkeypatch) -> None:  # noqa: ANN001
    client, *_ = steam_game
    use_es(monkeypatch, FakeEs(error=EsConnectionError("down")))
    r = client.get("/api/games/7/reviews")
    assert r.status_code == 503 and r.json()["error"]["code"] == "UNAVAILABLE"


@pytest.mark.parametrize("query", ["page=0", "size=0", "size=51", "sort=popular", "page=abc"])
def test_list_rejects_bad_query(steam_game, monkeypatch, query) -> None:  # noqa: ANN001
    client, *_ = steam_game
    es = use_es(monkeypatch, FakeEs(_result()))
    r = client.get(f"/api/games/7/reviews?{query}")
    assert r.status_code == 422 and r.json()["error"]["code"] == "INVALID_REQUEST"
    assert es.calls == []


def test_list_too_deep_page_is_422_without_calling_es(steam_game, monkeypatch) -> None:  # noqa: ANN001
    client, *_ = steam_game
    es = use_es(monkeypatch, FakeEs(_result()))
    r = client.get("/api/games/7/reviews?page=500&size=50")  # 시작 위치 24,950 > ES 한도 10,000
    assert r.status_code == 422 and r.json()["error"]["code"] == "INVALID_REQUEST"
    assert es.calls == []
    assert client.get("/api/games/7/reviews?page=200&size=50").status_code == 200  # 한도 안은 가능


def test_reviews_need_no_login(env, monkeypatch) -> None:  # noqa: ANN001
    from app.api.deps import get_current_user
    from app.main import app

    client, *_ = env
    app.dependency_overrides.pop(get_current_user)  # 가짜 로그인을 끈다: 세션 없는 방문자
    use_es(monkeypatch, FakeEs(_result()))
    assert client.get("/api/games/5/reviews").status_code == 200
    assert client.get("/api/games/5/reviews/summary").status_code == 200


# ---------- #27 요약 ----------
def test_summary_with_ai_row(env) -> None:  # noqa: ANN001
    client, engine, _ = env
    with seed(engine) as s:
        s.add(
            ReviewSummary(
                game_id=7,
                positive_ratio=0.9,
                pros_keywords="보스전, 탐험 ,아트",
                cons_keywords="최적화,난이도",
                summary="한두 줄 요약",
                generated_by="ai",
                updated_at=datetime(2026, 11, 24, 2, 30),
            )
        )
    assert client.get("/api/games/7/reviews/summary").json() == {
        "game_id": 7,
        "positive_ratio": 0.9,
        "summary": "한두 줄 요약",
        "pros": ["보스전", "탐험", "아트"],  # 쉼표로 나누고 공백을 정리
        "cons": ["최적화", "난이도"],
        "generated_by": "ai",
        "updated_at": "2026-11-24T02:30:00Z",
    }


def test_summary_ratio_matches_card_when_stats_exist(env) -> None:  # noqa: ANN001
    """긍정률은 카드와 같은 값: game_review_stats(한국어 79%)가 요약 행의 값보다 우선."""
    client, engine, _ = env
    with seed(engine) as s:
        s.add_all(
            [
                GameReviewStats(game_id=7, positive_pct_ko=79, positive_pct_all=87, updated_at=NOW),
                ReviewSummary(
                    game_id=7, positive_ratio=0.5, summary="요약", generated_by="ai", updated_at=NOW
                ),
            ]
        )
    assert client.get("/api/games/7/reviews/summary").json()["positive_ratio"] == 0.79
    assert client.get("/api/games/7").json()["positive_ratio"] == 0.79  # 카드(상세)와 같다


def test_summary_without_row_is_200_with_ratio_from_stats(env) -> None:  # noqa: ANN001
    client, engine, _ = env
    with seed(engine) as s:
        s.add(GameReviewStats(game_id=7, positive_pct_ko=None, positive_pct_all=87, updated_at=NOW))
    r = client.get("/api/games/7/reviews/summary")
    assert r.status_code == 200
    assert r.json() == {
        "game_id": 7,
        "positive_ratio": 0.87,
        "summary": None,
        "pros": [],
        "cons": [],
        "generated_by": None,
        "updated_at": None,
    }


def test_summary_with_no_data_at_all(env) -> None:  # noqa: ANN001
    client, *_ = env
    body = client.get("/api/games/7/reviews/summary").json()
    assert body["positive_ratio"] is None and body["summary"] is None and body["pros"] == []


def test_summary_fallback_row_and_empty_keywords(env) -> None:  # noqa: ANN001
    client, engine, _ = env
    with seed(engine) as s:
        s.add(
            ReviewSummary(
                game_id=7,
                pros_keywords=None,
                cons_keywords=" , ",
                summary=None,
                generated_by="fallback",
                updated_at=NOW,
            )
        )
    body = client.get("/api/games/7/reviews/summary").json()
    assert body["generated_by"] == "fallback" and body["pros"] == [] and body["cons"] == []


def test_summary_unknown_game_is_404(env) -> None:  # noqa: ANN001
    client, *_ = env
    r = client.get("/api/games/999999/reviews/summary")
    assert r.status_code == 404 and r.json()["error"]["code"] == "NOT_FOUND"
