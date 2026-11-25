"""찜 목록(#18), 목표가 목록(#20), 알림 내역(#21): games·prices_current 등을 조인해 채운다."""

from datetime import datetime
from decimal import Decimal

import pytest
from app.db.models import (
    Alert,
    AlertLog,
    GameGenre,
    GamePlatform,
    GameTimeToBeat,
    Genre,
    PlayerCount,
    PriceCurrent,
    ReviewSummary,
)
from app.main import app
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.conftest import NOW, seed


def _price(game_id, store, platform, cond, price, regular=None, pct=None) -> PriceCurrent:
    return PriceCurrent(
        game_id=game_id,
        store=store,
        edition="digital",
        platform=platform,
        item_condition=cond,
        price_krw=price,
        regular_krw=regular,
        discount_pct=pct,
        collected_at=NOW,
    )


@pytest.fixture
def seeded(env):
    client, engine, current = env
    with seed(engine) as s:
        s.add_all(
            [
                Genre(genre_id=1, name="액션"),
                Genre(genre_id=2, name="RPG"),
                GameGenre(game_id=119133, genre_id=2),
                GameGenre(game_id=119133, genre_id=1),
                GamePlatform(game_id=119133, platform="PS5"),
                GamePlatform(game_id=119133, platform="PC"),
                _price(119133, "steam", "PC", "new", 47900, 64800, 26),
                _price(119133, "epic", "PC", "new", 45000, 60000, 25),
                _price(119133, "danawa", "PS5", "used", 30000),  # 중고는 현재가에서 제외
                ReviewSummary(
                    game_id=119133,
                    positive_ratio=Decimal("0.920"),
                    generated_by="ai",
                    updated_at=NOW,
                ),
                PlayerCount(game_id=119133, player_count=100, collected_at=datetime(2026, 11, 1)),
                PlayerCount(
                    game_id=119133, player_count=412000, collected_at=datetime(2026, 11, 22)
                ),
                GameTimeToBeat(game_id=119133, normally_sec=216000, updated_at=NOW),
            ]
        )
    return client, engine, current


# ---------- #18 찜 목록 ----------
def test_wishlist_empty(env) -> None:
    client, *_ = env
    assert client.get("/api/me/wishlist").json() == {"items": [], "total": 0}


def test_wishlist_cards(seeded) -> None:
    client, _, current = seeded
    client.post("/api/me/wishlist", json={"game_id": 119133})
    client.post("/api/me/wishlist", json={"game_id": 5})
    current["id"] = 2
    client.post("/api/me/wishlist", json={"game_id": 7})  # 다른 사용자의 찜
    current["id"] = 1

    body = client.get("/api/me/wishlist").json()
    assert body["total"] == 2
    assert [i["game_id"] for i in body["items"]] == [5, 119133]  # 최근에 찜한 순

    elden = body["items"][1]
    assert elden == {
        "game_id": 119133,
        "name": "엘든 링",
        "name_en": "Elden Ring",
        "genres": ["액션", "RPG"],
        "platforms": ["PC", "PS5"],
        "cover_url": None,
        "price_krw": 45000,  # 새 상품 최저가 (epic)
        "regular_krw": 60000,
        "discount_pct": 25,
        "positive_ratio": 0.92,
        "concurrent_players": 412000,  # 가장 최근 값
        "time_to_beat_hours": 60,
        "critic_score": None,
        "wished": True,
    }
    empty = body["items"][0]  # 데이터가 없는 게임도 카드가 나온다
    assert empty["name"] == "Five" and empty["name_en"] == "Five"
    assert empty["genres"] == [] and empty["platforms"] == []
    assert empty["price_krw"] is None and empty["positive_ratio"] is None
    assert empty["concurrent_players"] is None and empty["time_to_beat_hours"] is None


# ---------- #20 목표가 목록 ----------
def test_alert_list(seeded) -> None:
    client, _, current = seeded
    first = client.post("/api/me/alerts", json={"game_id": 119133, "target_price_krw": 40000})
    client.post("/api/me/alerts", json={"game_id": 7, "target_price_krw": 1000})
    current["id"] = 2
    client.post("/api/me/alerts", json={"game_id": 5, "target_price_krw": 500})
    current["id"] = 1

    body = client.get("/api/me/alerts").json()
    assert body["total"] == 2
    assert [i["game_id"] for i in body["items"]] == [7, 119133]  # 최근에 만든 순
    elden = body["items"][1]
    assert elden["alert_id"] == first.json()["alert_id"]
    assert elden["game_name"] == "엘든 링"
    assert elden["target_price_krw"] == 40000
    assert elden["current_krw"] == 45000
    assert elden["active"] is True and elden["created_at"].endswith("Z")
    assert body["items"][0]["current_krw"] is None  # 가격 정보가 없는 게임


def test_alert_list_empty(env) -> None:
    client, *_ = env
    assert client.get("/api/me/alerts").json() == {"items": [], "total": 0}


# ---------- #21 알림 내역 ----------
def test_alert_logs_join(seeded) -> None:
    client, engine, current = seeded
    mine = client.post("/api/me/alerts", json={"game_id": 119133, "target_price_krw": 40000}).json()
    current["id"] = 2
    other = client.post("/api/me/alerts", json={"game_id": 7, "target_price_krw": 900}).json()
    current["id"] = 1
    with Session(engine) as s:  # alert_logs는 Backend가 쓰는 테이블
        s.add_all(
            [
                AlertLog(
                    alert_id=mine["alert_id"],
                    price_krw=39000,
                    store="steam",
                    sent_at=datetime(2026, 11, 20, 3, 0),
                ),
                AlertLog(
                    alert_id=mine["alert_id"],
                    price_krw=38000,
                    store="epic",
                    sent_at=datetime(2026, 11, 22, 3, 0),
                ),
                AlertLog(
                    alert_id=other["alert_id"],
                    price_krw=800,
                    store="gog",
                    sent_at=datetime(2026, 11, 22, 4, 0),
                ),
            ]
        )
        s.commit()

    body = client.get("/api/me/alerts/logs").json()
    assert body["total"] == 2  # 남의 내역은 없다
    assert [i["price_krw"] for i in body["items"]] == [38000, 39000]  # 최신순
    assert body["items"][0] == {
        "log_id": body["items"][0]["log_id"],
        "game_id": 119133,
        "game_name": "엘든 링",
        "price_krw": 38000,
        "target_price_krw": 40000,
        "store": "epic",
        "sent_at": "2026-11-22T03:00:00Z",
        "channel": "email",
    }


def test_alert_logs_empty(env) -> None:
    client, *_ = env
    assert client.get("/api/me/alerts/logs").json() == {"items": [], "total": 0}


def test_alerts_route_not_shadowed_by_id_route(env) -> None:
    client, *_ = env
    assert client.get("/api/me/alerts/logs").status_code == 200  # {alert_id}로 해석되지 않는다


# ---------- 로그인 ----------
@pytest.mark.parametrize("path", ["/api/me/wishlist", "/api/me/alerts", "/api/me/alerts/logs"])
def test_lists_require_login(path) -> None:
    app.dependency_overrides.clear()
    r = TestClient(app).get(path)
    assert r.status_code == 401 and r.json()["error"]["code"] == "UNAUTHORIZED"


def test_alert_model_still_writable(env) -> None:
    _, engine, _ = env
    with Session(engine) as s:
        s.add(Alert(user_id=1, game_id=5, target_price_krw=1, created_at=NOW))
        s.commit()  # 가드가 사용자 테이블은 막지 않는다
