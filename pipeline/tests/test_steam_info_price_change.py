"""refined.games_steam (Steam → games 칼럼 3개) 와 가격이 바뀐 때만 이력."""

import json
from pathlib import Path

from refiner.router import Maps, route
from refiner.rules import steam_info
from refiner.rules.price_change import LastPrices

ROOT = Path(__file__).resolve().parents[2]


def env(kind, payload, at="2026-11-23T00:00:00Z"):
    return {"source": "x", "kind": kind, "collected_at": at, "payload": payload}


def app_details(**data):
    return env("app_details", {"steam_appid": 5, "data": data})


def test_parse_rules():
    assert steam_info.age_rating("18") == 18
    assert steam_info.age_rating(0) == 0
    assert steam_info.age_rating("18+") == 18
    assert steam_info.age_rating(None) is None
    assert steam_info.korean_supported("English<strong>*</strong>, Korean") is True
    assert steam_info.korean_supported("영어, 한국어<strong>*</strong>") is True
    assert steam_info.korean_supported("English, Japanese") is False
    assert steam_info.korean_supported(None) is None
    assert steam_info.is_online([{"id": 2}, {"id": 36}]) is True
    assert steam_info.is_online([{"id": 2}, {"id": 24}]) is False  # 화면 분할은 온라인 아님
    assert steam_info.is_online(None) is None


def test_app_details_sends_games_steam_and_resends_with_game():
    maps = Maps({"steam": {5: 7}})
    r = route(
        app_details(required_age="15", supported_languages="Korean", categories=[{"id": 1}]), maps
    )
    msgs = [m for m in r["out"] if m[0] == "games_steam"]
    assert msgs[0][1] == "7"
    assert msgs[0][2]["payload"] == {
        "game_id": 7,
        "age_rating": 15,
        "korean_supported": True,
        "is_online": True,
        "updated_at": "2026-11-23T00:00:00Z",
    }
    # 게임 정보가 나중에 오면 Steam 값을 한 번 더 보낸다 (update 가 빈손이었을 수 있어서)
    g = route(env("game_info", {"id": 7, "name": "X"}), maps)
    assert [m[0] for m in g["out"]].count("games_steam") == 1
    # 매칭 안 되는 appid 는 보내지 않는다
    assert not [m for m in route(app_details(required_age=0), Maps())["out"]]


def test_app_details_without_fields_sends_nothing():
    r = route(app_details(name="X"), Maps({"steam": {5: 7}}))
    assert [m[0] for m in r["out"]] == []


def test_games_message_has_no_steam_columns_and_example_matches():
    g = route(env("game_info", {"id": 7, "name": "X"}), Maps())
    payload = g["out"][0][2]["payload"]
    assert not {"age_rating", "korean_supported", "is_online"} & set(payload)
    ex = json.loads(
        (ROOT / "docs/contracts/messages/refined.games_steam.json").read_text(encoding="utf-8")
    )
    assert ex["schema"]["fields"] == steam_info.REFINED_GAME_STEAM_SCHEMA["fields"]


def price_env(amount, at, currency="USD"):
    return env(
        "price",
        {
            "id": "abc",
            "deals": [
                {
                    "shop": {"id": 61, "name": "Steam"},
                    "price": {"amount": amount, "currency": currency},
                    "regular": {"amount": 59.99, "currency": currency},
                }
            ],
        },
        at,
    )


def history(r):
    return [m for m in r["out"] if m[0] == "price_history"]


def test_history_only_when_price_changes():
    maps = Maps({"itad": {"abc": 7}})
    first = history(route(price_env(29.99, "2026-11-01T00:00:00Z"), maps))
    assert len(first) == 1  # 처음 본 가격
    assert first[0][1] == "7:steam:digital:PC:new:2026-11-01T00:00:00Z"
    # 같은 가격: prices_current 는 갱신하지만 이력은 없다
    same = route(price_env(29.99, "2026-11-02T00:00:00Z"), maps)
    assert [m[0] for m in same["out"]].count("prices") == 1 and not history(same)
    # 다음 달 환율로 원화가 달라져도 원래 가격이 같으면 이력 없음
    assert not history(route(price_env(29.99, "2026-12-01T00:00:00Z"), maps))
    # 할인 시작 → 이력 1줄
    assert len(history(route(price_env(14.99, "2026-12-02T00:00:00Z"), maps))) == 1


def test_last_prices_save_and_load(tmp_path):
    p = tmp_path / "last.json"
    lp = LastPrices()
    row = {
        "game_id": 7,
        "store": "steam",
        "edition": "standard",
        "platform": "PC",
        "item_condition": "new",
        "price_krw": 1000,
        "price_original": 1000,
        "currency_original": "KRW",
        "regular_krw": 2000,
    }
    assert lp.is_new(row) is True
    lp.save(str(p))
    again = LastPrices.load(str(p))
    assert again.is_new(row) is False
    assert again.is_new({**row, "price_original": 900}) is True
