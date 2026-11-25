"""#8 장르·태그, #6 자동완성, #5 검색, #7 상세."""

from datetime import date, datetime
from decimal import Decimal

import pytest
from app.db.models import (
    Company,
    Game,
    GameAlias,
    GameCompany,
    GameGenre,
    GamePlatform,
    GameReviewStats,
    GameSeries,
    GameSeriesMap,
    GameStoreId,
    GameTag,
    GameTimeToBeat,
    Genre,
    PlayerCount,
    PriceCurrent,
    PriceHistory,
    Tag,
    Wishlist,
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


def test_search_sort_popular_matches_popular_ranking_and_keeps_unranked_last(catalog) -> None:
    client, engine, _ = catalog
    with seed(engine) as s:
        s.add_all(
            [
                Wishlist(user_id=1, game_id=11, created_at=NOW),
                Wishlist(user_id=2, game_id=11, created_at=NOW),
                Wishlist(user_id=1, game_id=10, created_at=NOW),
                PlayerCount(game_id=12, player_count=9000, collected_at=datetime(2026, 11, 20)),
            ]
        )
    by_name = _ids(client, "/api/games?size=100")
    popular = _ids(client, "/api/games?sort=popular&size=100")
    assert _ids(client, "/api/games/popular") == [11, 10, 12]  # 같은 기준: 찜 2 > 찜 1 > 동접자
    assert popular[:3] == [11, 10, 12]
    # 찜도 동접자도 없는 게임은 빠지지 않고 뒤에 이름순으로 이어진다
    assert popular[3:] == [i for i in by_name if i not in (11, 10, 12)]
    body = client.get("/api/games?sort=popular&size=2&page=2").json()
    assert body["total"] == len(by_name) and [i["game_id"] for i in body["items"]] == popular[2:4]


def test_search_sort_popular_with_filters_and_without_any_signal(catalog) -> None:
    client, engine, _ = catalog
    by_name = _ids(client, "/api/games?size=100")
    # 찜·동접자가 하나도 없으면 전체가 이름순 그대로다(인기 게임 API의 할인 대체 동작은 쓰지 않는다)
    assert _ids(client, "/api/games?sort=popular&size=100") == by_name
    with seed(engine) as s:
        s.add_all(
            [
                Wishlist(user_id=1, game_id=11, created_at=NOW),
                PlayerCount(game_id=12, player_count=500, collected_at=datetime(2026, 11, 20)),
            ]
        )
    assert _ids(client, "/api/games?sort=popular&genre=Action") == [11, 10]
    assert _ids(client, "/api/games?sort=popular&genre=RPG") == [12]
    assert _ids(client, "/api/games?sort=popular&platform=PC&q=hades") == [11, 10]


def _game(game_id, rating=None, count=None, **ttb) -> list:
    """평론 점수·클리어 시간이 있는 시험용 게임 (ttb 인자가 없으면 시간 행을 만들지 않는다)."""
    rows: list = [
        Game(
            game_id=game_id,
            name=f"G{game_id}",
            aggregated_rating=Decimal(str(rating)) if rating is not None else None,
            aggregated_rating_count=count,
            updated_at=NOW,
        )
    ]
    if ttb:
        rows.append(GameTimeToBeat(game_id=game_id, updated_at=NOW, **ttb))
    return rows


# ---------- 클리어 시간 3종·평론 점수 (#157) ----------
def test_detail_and_card_have_time_to_beat_and_critic_fields(catalog) -> None:
    client, engine, _ = catalog
    with seed(engine) as s:
        s.add_all(
            _game(
                40,
                86.5,
                24,
                hastily_sec=30600,
                normally_sec=43200,
                completely_sec=91800,
                ttb_count=842,
            )
            + _game(41, None, 5, hastily_sec=0, normally_sec=1800, completely_sec=None, ttb_count=0)
        )
    full = client.get("/api/games/40").json()
    assert full["time_to_beat"] == {
        "hastily_hours": 8.5,
        "normally_hours": 12.0,
        "completely_hours": 25.5,
        "count": 842,
    }
    assert (full["critic_score"], full["critic_count"]) == (87, 24)  # 86.5는 올림
    assert full["time_to_beat_hours"] == 12  # 카드의 기존 필드(보통, 정수)는 그대로

    partial = client.get(
        "/api/games/41"
    ).json()  # 0이거나 없는 값만 null, 짧은 게임도 0시간이 아니다
    assert partial["time_to_beat"] == {
        "hastily_hours": None,
        "normally_hours": 0.5,
        "completely_hours": None,
        "count": None,
    }
    assert (partial["critic_score"], partial["critic_count"]) == (None, None)  # 점수가 없으면 둘 다

    assert client.get("/api/games/10").json()["time_to_beat"] is None  # 시간 행이 없으면 null
    card = next(i for i in client.get("/api/games?size=100").json()["items"] if i["game_id"] == 40)
    assert card["critic_score"] == 87 and "critic_count" not in card  # 개수는 상세에만


def test_search_sort_rating_score_then_count_and_unrated_last(catalog) -> None:
    client, engine, _ = catalog
    with seed(engine) as s:
        s.add_all(_game(40, 86.5, 24) + _game(41, 90, 3) + _game(42, 90, 50) + _game(43))
    by_name = _ids(client, "/api/games?size=100")
    by_rating = _ids(client, "/api/games?sort=rating&size=100")
    assert by_rating[:3] == [42, 41, 40]  # 90(50명) > 90(3명) > 87
    assert by_rating[3:] == [i for i in by_name if i not in (42, 41, 40)]  # 점수 없는 게임은 이름순
    assert len(by_rating) == len(by_name)  # 제외되는 게임이 없다
    assert _ids(client, "/api/games?sort=rating&genre=Action") == [10, 11]  # 점수 없으면 이름순


def test_search_length_filter_buckets_and_combinations(catalog) -> None:
    client, engine, _ = catalog
    h = 3600
    with seed(engine) as s:
        s.add_all(
            _game(40, 80, 5, normally_sec=10 * h)  # 정확히 10시간 = 짧게
            + _game(41, 70, 5, normally_sec=10 * h + 1)  # 10시간 초과 = 보통
            + _game(42, 60, 5, normally_sec=40 * h)  # 정확히 40시간 = 보통
            + _game(43, 50, 5, normally_sec=40 * h + 1)  # 40시간 초과 = 길게
            + _game(44, 40, 5, normally_sec=0)  # 시간 정보 없음(0): 어느 구간에도 없다
            + _game(45, 30, 5)  # 시간 행 없음
        )
    assert _ids(client, "/api/games?length=short") == [40]
    assert _ids(client, "/api/games?length=medium") == [41, 42]
    assert _ids(client, "/api/games?length=long") == [43]
    assert _ids(client, "/api/games?length=medium&sort=rating") == [41, 42]
    assert _ids(client, "/api/games?length=medium&q=G42") == [42]
    body = client.get("/api/games?length=medium&size=1&page=2").json()
    assert body["total"] == 2 and [i["game_id"] for i in body["items"]] == [42]


def test_search_paging(catalog) -> None:
    client, *_ = catalog
    p1 = client.get("/api/games?size=2&page=1").json()
    p3 = client.get("/api/games?size=2&page=3").json()
    assert p1["total"] == 8 and len(p1["items"]) == 2 and len(p3["items"]) == 2
    assert client.get("/api/games?size=2&page=99").json()["items"] == []


@pytest.mark.parametrize(
    "query", ["sort=weird", "page=0", "size=0", "size=101", "length=weird", "q=" + "x" * 101]
)
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


# ---------- DB에 있던 칸을 상세로 내린 것 ----------
def _g(game_id, **kw) -> Game:
    return Game(game_id=game_id, name=f"Game {game_id}", updated_at=NOW, **kw)


def test_detail_exposes_stored_columns_companies_series_relations_and_review_stats(catalog) -> None:
    client, engine, _ = catalog
    with seed(engine) as s:
        s.add_all(
            [
                _g(
                    50,
                    korean_supported=True,
                    age_rating=0,
                    rating=Decimal("77.6"),
                    rating_count=120,
                ),
                _g(51, release_date=date(2011, 4, 5), cover_url="https://img/51"),
                _g(52),  # 출시일 없음: 시리즈 목록에서 뒤로
                _g(53, parent_game_id=50),  # 50의 DLC
                _g(54, version_parent_id=50),  # 50의 에디션
                Company(company_id=1, name="FromSoftware"),
                Company(company_id=2, name="Bandai Namco"),
                GameCompany(game_id=50, company_id=1, role="developer"),
                GameCompany(game_id=50, company_id=2, role="publisher"),
                GameSeries(series_id=9, kind="franchise", name="Souls"),
                GameSeriesMap(game_id=50, series_id=9, kind="franchise"),
                GameSeriesMap(game_id=51, series_id=9, kind="franchise"),
                GameSeriesMap(game_id=52, series_id=9, kind="franchise"),
                GameReviewStats(
                    game_id=50,
                    review_count_ko=120,
                    positive_pct_ko=91,
                    review_score_ko=8,
                    review_label_ko="매우 긍정적",
                    review_count_all=5000,
                    positive_pct_all=88,
                    review_label_all="대체로 긍정적",
                    updated_at=NOW,
                ),
            ]
        )
    body = client.get("/api/games/50").json()
    assert (body["korean_supported"], body["age_rating"]) == (True, 0)
    assert (body["user_score"], body["user_score_count"]) == (78, 120)  # 77.6 반올림
    assert body["developers"] == ["FromSoftware"] and body["publishers"] == ["Bandai Namco"]
    assert body["series"] == [
        {
            "kind": "franchise",
            "name": "Souls",
            "games": [  # 자기 자신은 빠지고, 출시일 있는 게임이 먼저
                {"game_id": 51, "name": "Game 51", "cover_url": "https://img/51"},
                {"game_id": 52, "name": "Game 52", "cover_url": None},
            ],
        }
    ]
    assert body["parent_game"] is None and body["version_parent"] is None
    assert [d["game_id"] for d in body["dlcs"]] == [53]
    assert [e["game_id"] for e in body["editions"]] == [54]
    assert body["review_stats"] == {
        "label_ko": "매우 긍정적",
        "count_ko": 120,
        "positive_pct_ko": 91,
        "score_ko": 8,
        "label_all": "대체로 긍정적",
        "count_all": 5000,
        "positive_pct_all": 88,
    }

    dlc = client.get("/api/games/53").json()
    assert dlc["parent_game"]["game_id"] == 50 and dlc["version_parent"] is None
    assert client.get("/api/games/54").json()["version_parent"]["game_id"] == 50


def test_detail_extras_are_empty_or_null_when_data_is_missing(catalog) -> None:
    client, *_ = catalog
    body = client.get("/api/games/10").json()  # catalog의 Hades: 부가 정보가 하나도 없다
    assert (body["korean_supported"], body["age_rating"]) == (None, None)
    assert (body["user_score"], body["user_score_count"]) == (None, None)
    assert body["developers"] == [] and body["publishers"] == [] and body["series"] == []
    assert body["parent_game"] is None and body["version_parent"] is None
    assert body["dlcs"] == [] and body["editions"] == [] and body["review_stats"] is None
