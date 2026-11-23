"""#9 인기, #25 짧게 끝낼 게임, #32 동접자 상위, #33 접속자 적은 온라인 게임."""

from datetime import datetime

import pytest
from app.db.models import Game, GameTimeToBeat, PlayerCount, Wishlist

from tests.conftest import NOW, seed


def _pc(game_id, count, day=20):
    return PlayerCount(game_id=game_id, player_count=count, collected_at=datetime(2026, 11, day))


def _ids(client, url):
    return [i["game_id"] for i in client.get(url).json()["items"]]


# ---------- #32 ----------
def test_players_top_uses_latest_count_desc(env) -> None:
    client, engine, _ = env
    with seed(engine) as s:
        s.add_all(
            [
                _pc(119133, 999999, day=1),  # 옛날 값은 무시, 최근 값(412000)을 쓴다
                _pc(119133, 412000, day=22),
                _pc(7, 500000, day=22),
                _pc(5, 0, day=22),  # 0명은 제외
            ]
        )
    body = client.get("/api/games/players/top").json()
    assert [i["game_id"] for i in body["items"]] == [7, 119133]
    assert body["items"][1]["concurrent_players"] == 412000
    assert set(body) == {"items"}
    assert _ids(client, "/api/games/players/top?size=1") == [7]


def test_players_top_empty(env) -> None:
    client, *_ = env
    assert client.get("/api/games/players/top").json() == {"items": []}


# ---------- #33 ----------
def test_players_low_only_online_and_below_threshold(env) -> None:
    client, engine, _ = env
    with seed(engine) as s:
        s.add_all(
            [
                _pc(5, 300),
                _pc(7, 50),
                _pc(119133, 2000),  # 임계값(1000) 이상 → 제외
                Game(game_id=20, name="Offline Low", is_online=False, updated_at=NOW),
                _pc(20, 10),  # 온라인 게임이 아님 → 제외
            ]
        )
        s.get(Game, 5).is_online = True
        s.get(Game, 7).is_online = True
        s.get(Game, 119133).is_online = True
    body = client.get("/api/games/players/low").json()
    assert [i["game_id"] for i in body["items"]] == [7, 5]  # 적은 순
    assert body["items"][0]["warning"] == "접속자가 적어 매칭이 어려울 수 있어요"
    assert body["items"][0]["concurrent_players"] == 50


def test_players_low_ignores_games_without_counts(env) -> None:
    client, engine, _ = env
    with seed(engine) as s:
        s.get(Game, 5).is_online = True  # 동접자 기록 없음
    assert client.get("/api/games/players/low").json() == {"items": []}


# ---------- #25 ----------
def test_short_games_under_10_hours_shortest_first(env) -> None:
    client, engine, _ = env
    with seed(engine) as s:
        s.add_all(
            [
                GameTimeToBeat(game_id=5, normally_sec=5 * 3600, updated_at=NOW),
                GameTimeToBeat(game_id=7, normally_sec=2 * 3600, updated_at=NOW),
                GameTimeToBeat(game_id=119133, normally_sec=60 * 3600, updated_at=NOW),  # 길다
            ]
        )
    body = client.get("/api/games/short").json()
    assert [i["game_id"] for i in body["items"]] == [7, 5]
    assert body["items"][0]["time_to_beat_hours"] == 2


def test_short_games_excludes_missing_or_zero_time(env) -> None:
    client, engine, _ = env
    with seed(engine) as s:
        s.add_all(
            [
                GameTimeToBeat(game_id=5, normally_sec=None, updated_at=NOW),
                GameTimeToBeat(game_id=7, normally_sec=0, updated_at=NOW),
                GameTimeToBeat(
                    game_id=119133, normally_sec=36000, updated_at=NOW
                ),  # 10시간 정확히는 포함
            ]
        )
    assert _ids(client, "/api/games/short") == [119133]


# ---------- #9 ----------
def test_popular_by_wishes_then_players(env) -> None:
    client, engine, _ = env
    with seed(engine) as s:
        s.add_all(
            [
                Wishlist(user_id=1, game_id=7, created_at=NOW),
                Wishlist(user_id=2, game_id=7, created_at=NOW),
                Wishlist(user_id=1, game_id=5, created_at=NOW),
                _pc(5, 1000),
                _pc(119133, 9000),  # 찜은 없지만 동접자가 있다
            ]
        )
    body = client.get("/api/games/popular").json()
    assert [i["game_id"] for i in body["items"]] == [7, 5, 119133]  # 찜 2 > 찜 1 > 찜 0
    assert all(i["wished"] is False for i in body["items"])


def test_popular_tie_on_wishes_uses_players_and_empty(env) -> None:
    client, engine, _ = env
    assert client.get("/api/games/popular").json() == {"items": []}
    with seed(engine) as s:
        s.add_all(
            [
                Wishlist(user_id=1, game_id=5, created_at=NOW),
                Wishlist(user_id=1, game_id=7, created_at=NOW),
                _pc(5, 10),
                _pc(7, 20),
            ]
        )
    assert _ids(client, "/api/games/popular") == [7, 5]


@pytest.mark.parametrize("path", ["popular", "short", "players/top", "players/low"])
def test_size_validation_and_not_shadowed(env, path) -> None:
    client, *_ = env
    assert (
        client.get(f"/api/games/{path}").status_code == 200
    )  # 상세(/games/{id})로 해석되지 않는다
    for size in ("0", "101", "x"):
        r = client.get(f"/api/games/{path}?size={size}")
        assert r.status_code == 422 and r.json()["error"]["code"] == "INVALID_REQUEST"
