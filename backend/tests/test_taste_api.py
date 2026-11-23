"""#24 내 취향 프로필, #23 플레이타임 기반 추천 (Steam 연동 필요)."""

from decimal import Decimal

import pytest
from app.db.models import (
    Game,
    GameGenre,
    GameStoreId,
    Genre,
    ReviewSummary,
    User,
    UserOwnedGame,
    Wishlist,
)
from app.main import app
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.conftest import NOW, seed


def _link_steam(engine, user_id=1) -> None:
    with Session(engine) as s:
        s.get(User, user_id).steam_id = "76561198000000000"
        s.commit()


def _own(user_id, appid, minutes) -> UserOwnedGame:
    return UserOwnedGame(
        user_id=user_id, steam_appid=appid, playtime_forever_min=minutes, updated_at=NOW
    )


@pytest.fixture
def played(env):
    """게임 5(Action+RPG, 앱 500, 3600분), 7(RPG, 앱 700, 1200분), 119133(Action, 미보유)."""
    client, engine, current = env
    _link_steam(engine)
    with seed(engine) as s:
        s.add_all(
            [
                Genre(genre_id=1, name="Action"),
                Genre(genre_id=2, name="RPG"),
                Genre(genre_id=3, name="Puzzle"),
                GameGenre(game_id=5, genre_id=1),
                GameGenre(game_id=5, genre_id=2),
                GameGenre(game_id=7, genre_id=2),
                GameGenre(game_id=119133, genre_id=1),
                Game(game_id=30, name="Puzzler", updated_at=NOW),
                GameGenre(game_id=30, genre_id=3),
                GameStoreId(game_id=5, store="steam", external_id="500"),
                GameStoreId(game_id=7, store="steam", external_id="700"),
                GameStoreId(game_id=119133, store="steam", external_id="1245620"),
                _own(1, 500, 3600),
                _own(1, 700, 1200),
                _own(
                    1, 999, 600
                ),  # games에 연결되지 않은 앱: 총 시간·보유 수에는 들어가고 장르에는 안 들어간다
                _own(2, 1245620, 9999),  # 다른 사용자의 보유 게임
            ]
        )
    return client, engine, current


# ---------- #24 ----------
def test_taste_requires_steam(env) -> None:
    client, *_ = env
    r = client.get("/api/me/taste")
    assert r.status_code == 400 and r.json()["error"]["code"] == "STEAM_REQUIRED"


def test_taste_profile(played) -> None:
    client, *_ = played
    body = client.get("/api/me/taste").json()
    assert body["total_playtime_hours"] == 90  # (3600+1200+600)분 = 5400분
    assert body["owned_games"] == 3
    # 장르별 플레이 분: Action 3600, RPG 4800 → 합 8400
    assert body["top_genres"] == [{"genre": "RPG", "pct": 57}, {"genre": "Action", "pct": 43}]
    assert body["style"] == "RPG·Action 장르를 즐기는 플레이어"


def test_taste_linked_but_no_owned_games(env) -> None:
    client, engine, _ = env
    _link_steam(engine)
    assert client.get("/api/me/taste").json() == {
        "total_playtime_hours": 0,
        "owned_games": 0,
        "top_genres": [],
        "style": "아직 취향을 분석할 데이터가 부족해요",
    }


def test_taste_is_per_user(played) -> None:
    client, engine, current = played
    current["id"] = 2
    _link_steam(engine, 2)
    body = client.get("/api/me/taste").json()
    assert body["owned_games"] == 1 and body["total_playtime_hours"] == 167


# ---------- #23 ----------
def test_recommendations_exclude_owned_and_explain(played) -> None:
    client, engine, _ = played
    with seed(engine) as s:
        s.add(Wishlist(user_id=1, game_id=119133, created_at=NOW))
    body = client.get("/api/me/recommendations").json()
    assert [i["game_id"] for i in body["items"]] == [
        119133
    ]  # 5·7은 보유, 30은 Puzzle(상위 장르 아님)
    item = body["items"][0]
    assert item["reason"] == "Action 장르를 많이 플레이했어요"
    assert item["wished"] is True and item["name"] == "엘든 링"


def test_recommendations_order_by_positive_ratio_and_size(played) -> None:
    client, engine, _ = played
    with seed(engine) as s:
        s.add_all(
            [
                Game(game_id=31, name="Rpg A", updated_at=NOW),
                Game(game_id=32, name="Rpg B", updated_at=NOW),
                GameGenre(game_id=31, genre_id=2),
                GameGenre(game_id=32, genre_id=2),
                ReviewSummary(
                    game_id=31, positive_ratio=Decimal("0.700"), generated_by="ai", updated_at=NOW
                ),
                ReviewSummary(
                    game_id=32, positive_ratio=Decimal("0.950"), generated_by="ai", updated_at=NOW
                ),
            ]
        )
    ids = [i["game_id"] for i in client.get("/api/me/recommendations").json()["items"]]
    assert ids == [32, 31, 119133]  # 긍정 비율 높은 순, 평가 없는 게임은 뒤
    assert len(client.get("/api/me/recommendations?size=1").json()["items"]) == 1
    reason = client.get("/api/me/recommendations").json()["items"][0]["reason"]
    assert reason == "RPG 장르를 많이 플레이했어요"  # RPG 4800분 > Action 3600분


def test_recommendations_empty_cases(env) -> None:
    client, engine, _ = env
    r = client.get("/api/me/recommendations")
    assert r.status_code == 400 and r.json()["error"]["code"] == "STEAM_REQUIRED"
    _link_steam(engine)
    assert client.get("/api/me/recommendations").json() == {"items": []}


@pytest.mark.parametrize("size", ["0", "51", "x"])
def test_recommendations_size_validation(played, size) -> None:
    client, *_ = played
    r = client.get(f"/api/me/recommendations?size={size}")
    assert r.status_code == 422 and r.json()["error"]["code"] == "INVALID_REQUEST"


@pytest.mark.parametrize("path", ["/api/me/taste", "/api/me/recommendations"])
def test_requires_login(path) -> None:
    app.dependency_overrides.clear()
    r = TestClient(app).get(path)
    assert r.status_code == 401 and r.json()["error"]["code"] == "UNAUTHORIZED"
