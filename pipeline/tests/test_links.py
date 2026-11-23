import json
from pathlib import Path

import pytest
from refiner.router import OUT_TOPICS, Maps, route
from refiner.rules.links import KEYWORD_TAG_OFFSET, LINK_FIELDS, alias_ok


def env(kind, payload, source="igdb", **kw):
    return {
        "source": source,
        "kind": kind,
        "collected_at": "2026-11-23T03:00:00Z",
        "payload": payload,
        **kw,
    }


GAME = {
    "id": 119133,
    "name": "Elden Ring",
    "first_release_date": 1645747200,
    "genres": [{"id": 12, "name": "Role-playing (RPG)"}],
    "involved_companies": [
        {"company": {"id": 248, "name": "Bandai Namco"}, "developer": False, "publisher": True},
        {"company": {"id": 1012, "name": "FromSoftware"}, "developer": True, "publisher": True},
        {"company": {"id": 9, "name": "Porter"}, "developer": False, "publisher": False},
    ],
    "themes": [{"id": 17, "name": "Fantasy"}],
    "keywords": [{"id": 72, "name": "exploration"}],
    "collections": [{"id": 3045, "name": "Elden Ring"}],
    "franchise": {"id": 999, "name": "Souls"},
    "platforms": [
        {"id": 6, "name": "PC (Microsoft Windows)"},
        {"id": 167, "name": "PlayStation 5"},
    ],
    "release_dates": [
        {"platform": {"name": "PC (Microsoft Windows)"}, "date": 1645747200},
        {"platform": {"name": "PlayStation 5"}, "date": 1645747200},
    ],
    "external_games": [{"external_game_source": 1, "uid": "1245620"}],
    "localizations": [{"name": "엘든 링", "region": {"name": "Korea"}}],
    "alternative_names": [{"id": 1, "name": "ER"}, {"id": 2, "name": "엘링"}],
}


def by_name(out):
    d = {}
    for name, key, msg in out:
        d.setdefault(name, []).append((key, msg["payload"]))
    return d


def test_game_info_fans_out_to_link_topics():
    res = route(env("game_info", GAME), Maps())
    d = by_name(res["out"])
    assert d["genres"] == [("12", {"genre_id": 12, "name": "Role-playing (RPG)"})]
    assert d["game_genres"][0][0] == "119133:12"
    roles = sorted(p["role"] for _, p in d["game_companies"])
    assert roles == ["developer", "publisher", "publisher"]  # 역할 없는 회사는 뺀다
    assert {p["company_id"] for _, p in d["companies"]} == {248, 1012}
    tag_ids = sorted(p["tag_id"] for _, p in d["tags"])
    assert tag_ids == [17, KEYWORD_TAG_OFFSET + 72]
    kinds = sorted(p["kind"] for _, p in d["game_series"])
    assert kinds == ["collection", "franchise"]
    assert {p["platform"]: p["release_date"] for _, p in d["game_platforms"]} == {
        "PC": "2022-02-25",
        "PS5": "2022-02-25",
    }
    aliases = [p["alias"] for _, p in d["game_aliases"]]
    assert aliases == ["Elden Ring", "엘든 링", "엘링"]  # 영문 2글자 ER 은 뺀다
    assert d["game_store_ids"][0][1] == {
        "game_id": 119133,
        "store": "steam",
        "external_id": "1245620",
    }


def test_message_fields_follow_contract_order():
    res = route(env("game_info", GAME), Maps())
    for name, _, msg in res["out"]:
        if name in LINK_FIELDS:
            assert list(msg["payload"]) == [f for f, _, _ in LINK_FIELDS[name]]
            assert [f["field"] for f in msg["schema"]["fields"]] == list(msg["payload"])


def test_all_link_topics_are_out_topics():
    for name in LINK_FIELDS:
        assert OUT_TOPICS[name] == f"refined.{name}"


def test_alias_rule():
    assert not alias_ok("ER") and not alias_ok("2") and alias_ok("몬헌") and alias_ok("RE4")


def test_time_to_beat():
    payload = [{"id": 1, "game_id": 17000, "hastily": 180000, "normally": 324000, "count": 11}]
    d = by_name(route(env("time_to_beat", payload), Maps())["out"])
    assert d["time_to_beat"][0][1]["normally_sec"] == 324000
    assert d["time_to_beat"][0][1]["completely_sec"] is None
    res = route(env("time_to_beat", {"hastily": 1}), Maps())
    assert res["out"] == [] and res["unmatched"]


def test_player_count():
    maps = Maps({"steam": {"1245620": 119133}})
    e = env(
        "player_count",
        {"response": {"player_count": 23405, "result": 1}},
        source="steam",
        request={"params": {"appid": 1245620}},
    )
    d = by_name(route(e, maps)["out"])
    assert d["player_counts"] == [
        (
            "119133:2026-11-23T03:00:00Z",
            {"game_id": 119133, "player_count": 23405, "collected_at": "2026-11-23T03:00:00Z"},
        )
    ]
    e2 = env("player_count", {"response": {"player_count": 5, "result": 1}}, source="steam")
    assert route(e2, maps)["unmatched"][0]["reason"].startswith("steam appid")


def test_price_sends_rates_once_per_day_and_learned_itad_id():
    maps = Maps({"steam": {"7": 7}})
    price = {
        "id": "itad-x",
        "deals": [
            {"shop": {"id": 61, "name": "Steam"}, "price": {"amount": 10, "currency": "KRW"}}
        ],
    }
    e = env("price", price, source="itad", request={"params": {"appid": "7"}})
    d = by_name(route(e, maps)["out"])
    assert sorted(p["currency"] for _, p in d["exchange_rates"]) == ["EUR", "GBP", "USD"]
    assert d["game_store_ids"][0][1] == {"game_id": 7, "store": "itad", "external_id": "itad-x"}
    d2 = by_name(route(e, maps)["out"])
    assert "exchange_rates" not in d2 and "game_store_ids" not in d2


@pytest.mark.parametrize("name", sorted(LINK_FIELDS))
def test_contract_examples_match_code(name):
    path = Path(__file__).resolve().parents[2] / "docs/contracts/messages/refined.links.json"
    if not path.exists():
        pytest.skip("refined.links.json은 contracts PR에서 추가된다")
    ex = json.loads(path.read_text(encoding="utf-8"))["topics"][name]
    assert [f["field"] for f in ex["schema"]["fields"]] == [f for f, _, _ in LINK_FIELDS[name]]
    assert list(ex["example"]) == [f for f, _, _ in LINK_FIELDS[name]]
