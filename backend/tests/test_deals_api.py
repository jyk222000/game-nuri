"""#13 할인 중 목록: 새 상품 현재가가 할인 중인 게임, 할인율 큰 순."""

from app.db.models import PriceCurrent

from tests.conftest import NOW, seed


def _p(game_id, store, price, pct, cond="new", platform="PC"):
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


def test_deals_sorted_by_discount(env) -> None:
    client, engine, _ = env
    with seed(engine) as s:
        s.add_all(
            [
                _p(119133, "steam", 47900, 26),
                _p(7, "steam", 1000, 60),
                _p(5, "steam", 500, 0),  # 할인 없음
                _p(5, "epic", 800, None),
            ]
        )
    body = client.get("/api/games/deals").json()
    assert [i["game_id"] for i in body["items"]] == [7, 119133]
    assert set(body) == {"items"}  # 페이지 없는 목록
    assert body["items"][0]["discount_pct"] == 60 and body["items"][0]["wished"] is False


def test_deals_excludes_used_and_cheaper_non_discounted(env) -> None:
    client, engine, _ = env
    with seed(engine) as s:
        s.add_all(
            [
                _p(7, "danawa", 100, 90, cond="used", platform="PS5"),  # 중고 할인은 제외
                # 현재가(최저가)는 할인 없는 epic 400이라 카드상 할인이 아니다 → 제외
                _p(5, "steam", 900, 50),
                _p(5, "epic", 400, 0),
            ]
        )
    assert client.get("/api/games/deals").json() == {"items": []}


def test_deals_size_and_validation(env) -> None:
    client, engine, _ = env
    with seed(engine) as s:
        s.add_all([_p(5, "steam", 1, 10), _p(7, "steam", 1, 20), _p(119133, "steam", 1, 30)])
    items = client.get("/api/games/deals?size=2").json()["items"]
    assert [i["game_id"] for i in items] == [119133, 7]
    for q in ("size=0", "size=101", "size=x"):
        r = client.get(f"/api/games/deals?{q}")
        assert r.status_code == 422 and r.json()["error"]["code"] == "INVALID_REQUEST"


def test_deals_empty(env) -> None:
    client, *_ = env
    assert client.get("/api/games/deals").json() == {"items": []}
