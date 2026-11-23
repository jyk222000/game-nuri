"""#8 장르·태그, #6 자동완성, #5 검색, #7 상세."""

from datetime import date, datetime

import pytest
from app.db.models import (
    Game,
    GameAlias,
    GameGenre,
    GamePlatform,
    GameStoreId,
    GameTag,
    Genre,
    PriceCurrent,
    PriceHistory,
    Tag,
)

from tests.conftest import NOW, seed


def _p(game_id, store, price, pct=None, cond="new", platform="PC"):
    return PriceCurrent(
        game_id=game_id,
        store=store,
        edition="digital",
        platform=platform,
        item_condition=cond,
        price_krw=price,
        regular_krw=price * 2,
        discount_pct=pct,
        collected_at=NOW,
    )


def _ids(client, url):
    body = client.get(url).json()
    return [i["game_id"] for i in body["items"]]


@pytest.fixture
def catalog(env):
    client, engine, current = env
    with seed(engine) as s:
        s.add_all(
            [
                Game(game_id=10, name="Hades", name_ko="하데스", updated_at=NOW),
                Game(game_id=11, name="Hades II", updated_at=NOW),
                Game(
                    game_id=12,
                    name="Red Dead Redemption 2",
                    name_ko="레드 데드 리뎀션 2",
                    updated_at=NOW,
                ),
                Game(game_id=13, name="100% Orange Juice", updated_at=NOW),
                Game(game_id=14, name="Under_Score", updated_at=NOW),
                Genre(genre_id=1, name="Action"),
                Genre(genre_id=2, name="RPG"),
                GameGenre(game_id=10, genre_id=1),
                GameGenre(game_id=11, genre_id=1),
                GameGenre(game_id=12, genre_id=2),
                GamePlatform(game_id=10, platform="PC"),
                GamePlatform(game_id=11, platform="PC"),
                GamePlatform(game_id=12, platform="PS5"),
                GameAlias(game_id=12, alias="레데리2", source="manual", reviewed=False),
                GameAlias(game_id=13, alias="레데리3", source="llm", reviewed=False),
                GameAlias(game_id=14, alias="언더", source="llm", reviewed=True),
                Tag(tag_id=1, name="Open world", source="igdb_theme", name_ko="오픈월드"),
                Tag(tag_id=2, name="Roguelike", source="igdb_keyword"),
                _p(10, "steam", 20000, 50),
                _p(11, "steam", 30000, 10),
                _p(12, "danawa", 50000, None, platform="PS5"),
            ]
        )
    return client, engine, current


# ---------- #8 ----------
def test_genres_and_tags(catalog) -> None:
    client, *_ = catalog
    assert client.get("/api/genres").json() == {"items": ["Action", "RPG"]}
    assert client.get("/api/tags").json() == {"items": ["Roguelike", "오픈월드"]}  # name_ko 우선


def test_genres_empty(env) -> None:
    client, *_ = env
    assert client.get("/api/genres").json() == {"items": []}
    assert client.get("/api/tags").json() == {"items": []}


# ---------- #6 ----------
def test_autocomplete_partial_korean_english_and_prefix_first(catalog) -> None:
    client, *_ = catalog
    r = client.get("/api/games/autocomplete?q=하데").json()
    assert r == {"items": [{"game_id": 10, "name": "하데스", "name_en": "Hades"}]}
    items = client.get("/api/games/autocomplete?q=hades").json()["items"]  # 대소문자 무시
    assert [i["game_id"] for i in items] == [10, 11]
    assert items[1] == {"game_id": 11, "name": "Hades II", "name_en": "Hades II"}
    assert _ids(client, "/api/games/autocomplete?q=dead") == [12]  # 중간 일치


def test_autocomplete_alias_rules(catalog) -> None:
    client, *_ = catalog
    assert _ids(client, "/api/games/autocomplete?q=레데리2") == [12]  # 수동 별칭은 검수 전에도 쓴다
    assert _ids(client, "/api/games/autocomplete?q=레데리3") == []  # AI 별칭은 검수 전이면 안 쓴다
    assert _ids(client, "/api/games/autocomplete?q=언더") == [14]  # 검수한 AI 별칭은 쓴다


def test_autocomplete_wildcards_are_literal_and_limit(catalog) -> None:
    client, *_ = catalog
    assert _ids(client, "/api/games/autocomplete?q=%25") == [13]
    assert _ids(client, "/api/games/autocomplete?q=_") == [14]
    assert len(_ids(client, "/api/games/autocomplete?q=a&limit=2")) == 2


@pytest.mark.parametrize("q", ["", "x" * 101])
def test_autocomplete_validation(catalog, q) -> None:
    client, *_ = catalog
    r = client.get("/api/games/autocomplete", params={"q": q})
    assert r.status_code == 422 and r.json()["error"]["code"] == "INVALID_REQUEST"
    assert client.get("/api/games/autocomplete").status_code == 422


def test_autocomplete_blank_is_empty(catalog) -> None:
    client, *_ = catalog
    assert client.get("/api/games/autocomplete?q=%20%20").json() == {"items": []}


# ---------- #5 ----------
def test_search_by_q_returns_cards_with_paging(catalog) -> None:
    client, *_ = catalog
    body = client.get("/api/games?q=hades").json()
    assert (body["total"], body["page"], body["size"]) == (2, 1, 20)
    assert [i["game_id"] for i in body["items"]] == [10, 11]
    card = body["items"][0]
    assert card["name"] == "하데스" and card["price_krw"] == 20000 and card["wished"] is False
    assert card["genres"] == ["Action"] and card["platforms"] == ["PC"]


def test_search_filters_platform_and_genre(catalog) -> None:
    client, *_ = catalog
    assert _ids(client, "/api/games?platform=PS5") == [12]
    assert client.get("/api/games?genre=Action").json()["total"] == 2
    assert _ids(client, "/api/games?genre=Action&platform=PC&q=II") == [11]
    assert client.get("/api/games?platform=Switch").json() == {
        "items": [],
        "total": 0,
        "page": 1,
        "size": 20,
    }


def test_search_sort_price_and_discount(catalog) -> None:
    client, *_ = catalog
    assert _ids(client, "/api/games?sort=price")[:3] == [10, 11, 12]  # 가격 없는 게임은 뒤
    by_discount = _ids(client, "/api/games?sort=discount")
    assert by_discount[:2] == [10, 11]  # 할인 없는 게임(12 포함)은 뒤


def test_search_paging(catalog) -> None:
    client, *_ = catalog
    p1 = client.get("/api/games?size=2&page=1").json()
    p3 = client.get("/api/games?size=2&page=3").json()
    assert p1["total"] == 8 and len(p1["items"]) == 2 and len(p3["items"]) == 2
    assert client.get("/api/games?size=2&page=99").json()["items"] == []


@pytest.mark.parametrize("query", ["sort=weird", "page=0", "size=0", "size=101", "q=" + "x" * 101])
def test_search_validation(catalog, query) -> None:
    client, *_ = catalog
    r = client.get(f"/api/games?{query}")
    assert r.status_code == 422 and r.json()["error"]["code"] == "INVALID_REQUEST"


# ---------- #7 ----------
def test_detail(catalog) -> None:
    client, engine, _ = catalog
    with seed(engine) as s:
        game = s.get(Game, 10)
        game.summary = "로그라이크"
        game.release_date = date(2020, 9, 17)
        game.is_online = False
        s.add_all(
            [
                GameTag(game_id=10, tag_id=1),
                GameTag(game_id=10, tag_id=2),
                GameStoreId(game_id=10, store="steam", external_id="1145360"),
                GameStoreId(game_id=10, store="epic", external_id="abc"),
                PriceHistory(
                    id=1,
                    game_id=10,
                    store="steam",
                    edition="digital",
                    platform="PC",
                    item_condition="new",
                    price_krw=15000,
                    collected_at=datetime(2026, 1, 1),
                ),
            ]
        )
    body = client.get("/api/games/10").json()
    assert body["game_id"] == 10 and body["name"] == "하데스" and body["price_krw"] == 20000
    assert body["release_date"] == "2020-09-17" and body["summary"] == "로그라이크"
    assert body["tags"] == ["Roguelike", "오픈월드"]
    assert body["online_only"] is False and body["steam_app_id"] == 1145360
    assert body["lowest_krw"] == 15000  # 이력 최저가가 현재가보다 낮다
    assert body["insights"] == []


def test_detail_minimal_game(catalog) -> None:
    client, *_ = catalog
    body = client.get("/api/games/13").json()
    assert body["release_date"] is None and body["summary"] is None and body["tags"] == []
    assert body["steam_app_id"] is None and body["lowest_krw"] is None
    assert body["online_only"] is False


def test_detail_404_422(catalog) -> None:
    client, *_ = catalog
    r = client.get("/api/games/999")
    assert r.status_code == 404 and r.json()["error"]["code"] == "NOT_FOUND"
    assert client.get("/api/games/abc").status_code == 422


def test_static_routes_not_shadowed_by_detail(catalog) -> None:
    client, *_ = catalog
    assert client.get("/api/games/autocomplete?q=h").status_code == 200
    assert "total" not in client.get("/api/games/deals").json()  # deals는 detail로 해석되지 않는다
