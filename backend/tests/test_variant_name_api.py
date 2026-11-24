"""가격 응답의 variant_name(#93): 본편이면 null, 에디션이면 이름. prices·history·lowest 공통."""

from datetime import timedelta

import pytest
from app.core import keys
from app.db.models import PriceCurrent, PriceHistory
from app.services import prices as prices_service

from tests.conftest import NOW, seed

EDITION = "얼티밋 에디션"


class FakeValkey:
    def __init__(self) -> None:
        self.data: dict[str, str] = {}

    def get(self, key):  # noqa: ANN001
        return self.data.get(key)

    def set(self, key, value, ex=None):  # noqa: ANN001
        self.data[key] = value


@pytest.fixture
def valkey(monkeypatch):  # noqa: ANN001
    v = FakeValkey()
    monkeypatch.setattr(prices_service, "get_valkey", lambda: v)
    return v


def _cur(game_id, platform, price, store="danawa", variant=None, cond="new"):
    return PriceCurrent(
        game_id=game_id,
        store=store,
        edition="physical" if store == "danawa" else "digital",
        platform=platform,
        item_condition=cond,
        price_krw=price,
        regular_krw=None if store == "danawa" else price * 2,
        discount_pct=None,
        url=f"https://example.com/{store}",
        variant_name=variant,
        collected_at=NOW,
    )


def _hist(hid, game_id, platform, price, days_ago, store="danawa", variant=None):
    return PriceHistory(
        id=hid,
        game_id=game_id,
        store=store,
        edition="physical",
        platform=platform,
        item_condition="new",
        price_krw=price,
        regular_krw=None,
        discount_pct=None,
        variant_name=variant,
        collected_at=NOW - timedelta(days=days_ago),
    )


def test_prices_items_carry_variant_name_and_pc_stays_null(env, valkey) -> None:  # noqa: ANN001
    client, engine, _ = env
    with seed(engine) as s:
        s.add_all(
            [
                _cur(7, "PC", 19770, store="msstore"),
                _cur(7, "PS5", 42800, variant=EDITION),  # 본편이 없는 플랫폼의 에디션 가격
            ]
        )
    items = {
        i["platform"]: i["variant_name"] for i in client.get("/api/games/7/prices").json()["items"]
    }
    assert items == {"PC": None, "PS5": EDITION}


def test_prices_lowest_variant_follows_the_chosen_row(env, valkey) -> None:  # noqa: ANN001
    client, engine, _ = env
    with seed(engine) as s:
        s.add_all([_cur(7, "PC", 19770, store="msstore"), _cur(7, "PS5", 11810, variant=EDITION)])
        s.add(_cur(5, "PS5", 42800, variant=EDITION))  # 콘솔 전용 게임
    # PC 우선이라 현재가(lowest)는 PC의 값이고 에디션 이름은 없다
    assert client.get("/api/games/7/prices").json()["lowest"]["variant_name"] is None
    # 콘솔 전용 게임은 에디션 가격이 현재가이고, 이름이 같이 나간다
    lowest = client.get("/api/games/5/prices").json()["lowest"]
    assert lowest["platform"] == "PS5" and lowest["variant_name"] == EDITION


def test_history_items_carry_variant_name(env) -> None:  # noqa: ANN001
    client, engine, _ = env
    with seed(engine) as s:
        s.add_all(
            [
                _hist(1, 5, "PS5", 45000, 5, variant=EDITION),
                _hist(2, 5, "PS5", 42800, 1, variant=EDITION),
            ]
        )
        s.add(_hist(3, 7, "PC", 19770, 1, store="msstore"))
    assert [i["variant_name"] for i in client.get("/api/games/5/history").json()["items"]] == [
        EDITION
    ] * 2
    assert client.get("/api/games/7/history").json()["items"][0]["variant_name"] is None


def test_lowest_items_carry_variant_name(env) -> None:  # noqa: ANN001
    client, engine, _ = env
    with seed(engine) as s:
        s.add_all(
            [
                _hist(1, 5, "PS5", 45000, 9, variant=EDITION),
                _hist(2, 5, "PS5", 39800, 3, variant=EDITION),
                _hist(3, 5, "Switch2", 81800, 2),  # 본편 가격
            ]
        )
    by_platform = {i["platform"]: i for i in client.get("/api/games/5/lowest").json()["items"]}
    assert (
        by_platform["PS5"]["price_krw"] == 39800 and by_platform["PS5"]["variant_name"] == EDITION
    )
    assert by_platform["Switch2"]["variant_name"] is None


def test_stale_cache_without_variant_name_is_ignored_and_rebuilt(env, valkey) -> None:  # noqa: ANN001
    """배포 직후 Valkey에 남은 옛 값(variant_name 없음)은 오류 없이 버리고 DB에서 새로 만든다."""
    client, engine, _ = env
    with seed(engine) as s:
        s.add(_cur(5, "PS5", 42800, variant=EDITION))
    valkey.data[keys.price_cache_key(5)] = (
        '{"game_id":5,"items":[{"store":"danawa","edition":"physical","platform":"PS5",'
        '"item_condition":"new","price_krw":99999,"regular_krw":null,"discount_pct":null,'
        '"url":null,"collected_at":"2026-11-23T00:00:00Z"}],'
        '"lowest":{"store":"danawa","edition":"physical","platform":"PS5",'
        '"item_condition":"new","price_krw":99999}}'
    )
    r = client.get("/api/games/5/prices")
    assert r.status_code == 200
    body = r.json()
    assert body["items"][0]["price_krw"] == 42800 and body["items"][0]["variant_name"] == EDITION
    assert body["lowest"]["variant_name"] == EDITION
    assert '"variant_name"' in valkey.data[keys.price_cache_key(5)]  # 새 값으로 다시 저장됨
