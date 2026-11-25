"""#10 스토어별 가격 비교 + Valkey 캐시(fail-open)."""

import pytest
import redis
from app.core import keys
from app.db.models import PriceCurrent
from app.services import prices as prices_service

from tests.conftest import NOW, seed


def _row(game_id, store, platform, cond, price, edition="digital", regular=None, pct=None):
    return PriceCurrent(
        game_id=game_id,
        store=store,
        edition=edition,
        platform=platform,
        item_condition=cond,
        price_krw=price,
        regular_krw=regular,
        discount_pct=pct,
        url=f"https://example.com/{store}",
        collected_at=NOW,
    )


class FakeValkey:
    def __init__(self) -> None:
        self.data: dict[str, str] = {}
        self.ttl: dict[str, int] = {}
        self.reads = 0

    def get(self, key):  # noqa: ANN001
        self.reads += 1
        return self.data.get(key)

    def set(self, key, value, ex=None):  # noqa: ANN001
        self.data[key] = value
        self.ttl[key] = ex


class DeadValkey:
    def get(self, key):  # noqa: ANN001
        raise redis.ConnectionError("down")

    def set(self, key, value, ex=None):  # noqa: ANN001
        raise redis.ConnectionError("down")


@pytest.fixture
def fake(monkeypatch):
    v = FakeValkey()
    monkeypatch.setattr(prices_service, "get_valkey", lambda: v)
    return v


@pytest.fixture
def priced(env, fake):
    client, engine, current = env
    with seed(engine) as s:
        s.add_all(
            [
                _row(119133, "steam", "PC", "new", 47900, regular=64800, pct=26),
                _row(119133, "epic", "PC", "new", 45000, regular=60000, pct=25),
                _row(119133, "danawa", "PS5", "used", 30000, edition="physical"),
            ]
        )
    return client, engine, fake


def test_prices_items_and_lowest(priced) -> None:
    client, *_ = priced
    r = client.get("/api/games/119133/prices")
    assert r.status_code == 200
    body = r.json()
    assert body["game_id"] == 119133
    assert [i["store"] for i in body["items"]] == ["danawa", "epic", "steam"]  # 가격 낮은 순
    assert body["items"][2] == {
        "store": "steam",
        "edition": "digital",
        "platform": "PC",
        "item_condition": "new",
        "price_krw": 47900,
        "regular_krw": 64800,
        "discount_pct": 26,
        "url": "https://example.com/steam",
        "variant_name": None,
        "price_original": None,
        "currency_original": None,
        "collected_at": "2026-11-23T00:00:00Z",
    }
    # 중고(30000)가 더 싸도 현재가(lowest)는 새 상품 기준
    assert body["lowest"] == {
        "store": "epic",
        "edition": "digital",
        "platform": "PC",
        "item_condition": "new",
        "price_krw": 45000,
        "variant_name": None,
    }


def test_prices_no_new_item_means_lowest_null(env, fake) -> None:
    client, engine, _ = env
    with seed(engine) as s:
        s.add(_row(7, "danawa", "PS5", "used", 30000, edition="physical"))
    body = client.get("/api/games/7/prices").json()
    assert len(body["items"]) == 1 and body["lowest"] is None


def test_prices_game_without_prices(env, fake) -> None:
    client, *_ = env
    assert client.get("/api/games/5/prices").json() == {"game_id": 5, "items": [], "lowest": None}


def test_prices_unknown_game_404_and_not_cached(env, fake) -> None:
    client, *_ = env
    r = client.get("/api/games/999/prices")
    assert r.status_code == 404 and r.json()["error"]["code"] == "NOT_FOUND"
    assert fake.data == {}


def test_prices_invalid_game_id_422(env, fake) -> None:
    client, *_ = env
    r = client.get("/api/games/abc/prices")
    assert r.status_code == 422 and r.json()["error"]["code"] == "INVALID_REQUEST"


# ---------- 캐시 ----------
def test_prices_cached_with_ttl_and_served_from_cache(priced) -> None:
    client, engine, fake = priced
    first = client.get("/api/games/119133/prices").json()
    key = keys.price_cache_key(119133)
    assert key in fake.data and fake.ttl[key] == 600  # 10분

    with seed(engine) as s:  # DB를 바꿔도 캐시가 살아 있는 동안은 캐시 값
        s.merge(_row(119133, "gog", "PC", "new", 100))
    assert client.get("/api/games/119133/prices").json() == first


def test_prices_cache_miss_after_expire(priced) -> None:
    client, engine, fake = priced
    client.get("/api/games/119133/prices")
    fake.data.clear()  # TTL 만료와 같다
    with seed(engine) as s:
        s.merge(_row(119133, "gog", "PC", "new", 100))
    assert client.get("/api/games/119133/prices").json()["lowest"]["price_krw"] == 100


def test_prices_valkey_down_still_200(env, monkeypatch) -> None:
    client, engine, _ = env
    monkeypatch.setattr(prices_service, "get_valkey", lambda: DeadValkey())
    with seed(engine) as s:
        s.add(_row(119133, "steam", "PC", "new", 47900))
    r = client.get("/api/games/119133/prices")
    assert r.status_code == 200 and r.json()["lowest"]["price_krw"] == 47900


def test_prices_broken_cache_value_ignored(priced) -> None:
    client, _, fake = priced
    fake.data[keys.price_cache_key(119133)] = "{not json"
    assert client.get("/api/games/119133/prices").status_code == 200


def test_lowest_is_pc_first_even_when_console_is_cheaper(env, fake) -> None:
    """items는 모든 플랫폼을 가격순으로 보이지만, 현재가(lowest)는 카드·타이밍처럼 PC 기준이다."""
    client, engine, _ = env
    with seed(engine) as s:
        s.add_all(
            [
                _row(5, "msstore", "PC", "new", 19770, regular=65900, pct=70),
                _row(5, "danawa", "PS4", "new", 11810),
            ]
        )
    body = client.get("/api/games/5/prices").json()
    assert [i["platform"] for i in body["items"]] == ["PS4", "PC"]  # 콘솔 값도 목록에는 그대로
    assert body["lowest"]["platform"] == "PC" and body["lowest"]["price_krw"] == 19770


def test_lowest_for_console_only_game_uses_console(env, fake) -> None:
    client, engine, _ = env
    with seed(engine) as s:
        s.add_all(
            [_row(5, "danawa", "PS5", "new", 42800), _row(5, "danawa", "Switch2", "new", 81800)]
        )
    lowest = client.get("/api/games/5/prices").json()["lowest"]
    assert lowest["platform"] == "PS5" and lowest["price_krw"] == 42800


def test_prices_expose_original_currency_price(env, fake) -> None:
    client, engine, _ = env
    row = _row(119133, "steam", "PC", "new", 83000, regular=83000)
    row.price_original, row.currency_original = 59.99, "USD"
    with seed(engine) as s:
        s.add_all([row, _row(119133, "epic", "PC", "new", 90000)])
    items = {i["store"]: i for i in client.get("/api/games/119133/prices").json()["items"]}
    assert (items["steam"]["price_original"], items["steam"]["currency_original"]) == (59.99, "USD")
    assert (items["epic"]["price_original"], items["epic"]["currency_original"]) == (None, None)
