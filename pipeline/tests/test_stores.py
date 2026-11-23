"""ITAD 판매처 → refined.stores."""

import json
from pathlib import Path

from refiner.router import Maps, route
from refiner.rules import stores

ROOT = Path(__file__).resolve().parents[2]
MSG = ROOT / "docs/contracts/messages"


def price_env(shops, at="2026-11-23T00:00:00Z"):
    deals = [
        {"shop": s, "price": {"amount": 10000, "currency": "KRW"}, "regular": None} for s in shops
    ]
    return {
        "source": "itad",
        "kind": "price",
        "collected_at": at,
        "payload": {"id": "abc", "deals": deals},
    }


def names(r):
    return [m[1] for m in r["out"] if m[0] == "stores"]


def test_store_row_uses_seed_names_and_itad_id():
    assert stores.store_row({"id": 61, "name": "Steam"}) == {
        "store": "steam",
        "display_name": "Steam",
        "platform": "pc",
        "itad_shop_id": 61,
    }
    epic = stores.store_row({"id": 16, "name": "Epic Game Store"})
    assert (epic["store"], epic["display_name"], epic["itad_shop_id"]) == (
        "epic",
        "Epic Games Store",
        16,
    )
    other = stores.store_row({"id": 6, "name": "Fanatical"})
    assert (other["store"], other["display_name"]) == ("fanatical", "Fanatical")
    assert stores.store_row({}) is None


def test_price_sends_each_store_once_per_run():
    maps = Maps({"itad": {"abc": 7}})
    shops = [{"id": 61, "name": "Steam"}, {"id": 6, "name": "Fanatical"}]
    assert names(route(price_env(shops), maps)) == ["steam", "fanatical"]
    assert names(route(price_env(shops), maps)) == []  # 같은 실행에서는 다시 보내지 않는다
    assert names(route(price_env([{"id": 35, "name": "GOG"}]), maps)) == ["gog"]


def test_unmatched_game_sends_no_store():
    assert names(route(price_env([{"id": 61, "name": "Steam"}]), Maps())) == []


def test_history_sends_stores_and_matches_contract():
    env = {
        "source": "itad",
        "kind": "price_history",
        "collected_at": "2026-11-23T00:00:00Z",
        "request": {"params": {}},
        "payload": {
            "id": "abc",
            "history": [
                {
                    "timestamp": "2024-01-01T00:00:00+00:00",
                    "shop": {"id": 61, "name": "Steam"},
                    "deal": {"price": {"amount": 1000, "currency": "KRW"}},
                }
            ],
        },
    }
    r = route(env, Maps({"itad": {"abc": 7}}))
    (msg,) = [m[2] for m in r["out"] if m[0] == "stores"]
    ex = json.loads((MSG / "refined.stores.json").read_text(encoding="utf-8"))
    assert msg["schema"] == ex["schema"] and msg["payload"] == ex["payload"]
