import json

from refiner.build_id_map import rows_to_maps
from refiner.main import load_maps, save_maps
from refiner.router import Maps, route, steam_hint


def env(kind, payload, **kw):
    return {
        "source": "x",
        "kind": kind,
        "collected_at": "2026-11-23T00:00:00Z",
        "payload": payload,
        **kw,
    }


REQ_HTML = "<strong>최소:</strong><br><ul><li><strong>운영 체제:</strong> Windows 10</li></ul>"

GAME = {
    "id": 119133,
    "name": "Elden Ring",
    "external_games": [{"external_game_source": 1, "uid": "1245620"}],
    "localizations": [{"name": "엘든 링", "region": {"name": "Korea"}}],
}
PRICE = {
    "id": "itad-1",
    "deals": [
        {
            "shop": {"id": 61, "name": "Steam"},
            "price": {"amount": 47900, "currency": "KRW"},
            "regular": {"amount": 64800, "currency": "KRW"},
            "cut": 26,
            "url": "u",
        }
    ],
}


def test_empty_map_learns_steam_from_igdb_then_links_requirements():
    maps = Maps()
    route(env("game_info", GAME), maps)
    assert maps.steam == {1245620: 119133} and maps.changed
    res = route(
        env(
            "app_details",
            {
                "steam_appid": 1245620,
                "data": {"pc_requirements": {"minimum": REQ_HTML}},
            },
        ),
        maps,
    )
    assert [o[0] for o in res["out"]] == ["requirements"] and res["unmatched"] == []


def test_itad_linked_by_steam_hint_and_learned():
    maps = Maps({"steam": {"1245620": 119133}})
    no_hint = route(env("price", PRICE), maps)
    assert no_hint["out"] == [] and "매칭 실패" in no_hint["unmatched"][0]["reason"]
    res = route(env("price", PRICE, request={"params": {"appid": "app/1245620"}}), maps)
    assert res["out"][0][1] == "119133:steam:digital:PC:new"
    assert maps.itad == {"itad-1": 119133}
    assert route(env("price", PRICE), maps)["out"]  # 다음부터는 힌트 없이도 연결


def test_steam_hint_places():
    assert steam_hint({"payload": {"steam_appid": 7}}) == 7
    assert steam_hint({"request": {"params": {"steam_appid": "8"}}}) == 8
    assert steam_hint({"payload": {}}) is None


def test_learning_does_not_overwrite_existing():
    maps = Maps({"steam": {"1245620": 1}})
    route(env("game_info", GAME), maps)
    assert maps.steam[1245620] == 1


def test_state_file_round_trip(tmp_path):
    base = tmp_path / "id_map.json"
    base.write_text(json.dumps({"itad": {"a": 1}}), encoding="utf-8")
    state = tmp_path / "state" / "learned.json"
    maps = load_maps(str(base), str(state))
    route(env("game_info", GAME), maps)
    save_maps(maps, str(state))
    again = load_maps(str(base), str(state))
    assert again.itad == {"a": 1} and again.steam == {1245620: 119133} and not again.changed


def test_build_id_map_rows():
    rows = [
        {
            "igdb_id": "119133",
            "steam_appid": "1245620",
            "itad_id": "x",
            "name": "Elden Ring",
            "name_ko": "엘든 링",
            "aliases": "엘든링",
        },
        {"igdb_id": "", "steam_appid": "1"},
        {"igdb_id": "5", "steam_appid": "1245620"},
    ]
    m, warnings = rows_to_maps(rows)
    assert m.steam == {1245620: 119133} and m.itad == {"x": 119133}
    assert len(warnings) == 2 and m.alias
