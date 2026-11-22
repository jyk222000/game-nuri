import json
from pathlib import Path

import pytest
from refiner.router import Maps, route
from refiner.rules.console import infer_edition, refine_console_price
from refiner.rules.game import REFINED_GAME_FIELDS, refine_game, to_connect_message, unix_to_date
from refiner.rules.requirements import html_to_text, refine_requirements

AT = "2026-11-19T02:30:00Z"


def env(kind, payload):
    return {
        "schema_version": 1,
        "kind": kind,
        "source": "x",
        "collected_at": AT,
        "payload": payload,
    }


# ---- games ----
def igdb_payload(**kw):
    p = {
        "id": 119133,
        "name": "Elden Ring",
        "first_release_date": 1645747200,
        "slug": "elden-ring",
        "game_type": {"id": 0},
        "parent_game": None,
        "cover": {"image_id": "co4jni"},
        "total_rating": 95.1234,
        "total_rating_count": 10,
        "platforms": [
            {"name": "PlayStation 5"},
            {"name": "PC (Microsoft Windows)"},
            {"name": "Mac"},
        ],
        "external_games": [
            {"external_game_source": 1, "uid": "1245620"},
            {"external_game_source": 5, "uid": "x"},
        ],
        "localizations": [
            {"name": "エルデンリング", "region": {"name": "Japan"}},
            {"name": "엘든 링", "region": {"name": "Korea"}},
        ],
    }
    p.update(kw)
    return p


def test_game_row_columns_dates_and_korean_name():
    rows, extras, un = refine_game(env("game_info", igdb_payload()))
    r = rows[0]
    assert un == [] and set(r) == {f for f, _, _ in REFINED_GAME_FIELDS}
    assert (r["release_date"], r["name_ko"], r["rating"], r["game_type"]) == (
        "2022-02-25",
        "엘든 링",
        95.12,
        0,
    )
    assert r["cover_url"].endswith("/co4jni.jpg") and r["updated_at"] == AT
    assert r["age_rating"] is None  # Steam 쪽 값은 이 메시지에 없다


def test_game_platforms_mapped_and_unserved_skipped_and_steam_id():
    _, extras, _ = refine_game(env("game_info", igdb_payload()))
    assert extras["platforms"] == ["PS5", "PC"] and extras["skipped_platforms"] == ["Mac"]
    assert extras["store_ids"] == [("steam", "1245620")]


def test_game_blank_becomes_null_and_missing_id_is_unmatched():
    rows, _, _ = refine_game(env("game_info", igdb_payload(summary="  ", slug="")))
    assert rows[0]["summary"] is None and rows[0]["slug"] is None
    rows, _, un = refine_game(env("game_info", {"name": "x"}))
    assert rows == [] and len(un) == 1


def test_unix_to_date():
    assert unix_to_date(None) is None and unix_to_date(0) == "1970-01-01"


def test_game_message_matches_contract_example():
    rows, _, _ = refine_game(env("game_info", igdb_payload()))
    msg = to_connect_message(rows[0])
    assert [f["field"] for f in msg["schema"]["fields"]] == list(msg["payload"])


# ---- requirements ----
HTML = (
    "<strong>최소:</strong><br><ul><li><strong>운영 체제:</strong> Windows 10<br></li>"
    "<li><strong>메모리:</strong> 12 GB RAM<br></li></ul>"
)


def test_html_to_text_and_blank():
    assert html_to_text(HTML) == "OS: Windows 10 / RAM: 12 GB RAM"
    assert html_to_text("") is None and html_to_text(None) is None


def test_requirements_both_payload_shapes():
    data = {"pc_requirements": {"minimum": HTML, "recommended": ""}}
    for payload in ({"steam_appid": 7, "data": data}, {"7": {"success": True, "data": data}}):
        rows, un = refine_requirements(env("app_details", payload), {7: 119133}.get)
        assert un == [] and rows == [
            {
                "game_id": 119133,
                "minimum_text": "OS: Windows 10 / RAM: 12 GB RAM",
                "recommended_text": None,
                "updated_at": AT,
            }
        ]


def test_requirements_unknown_appid_unmatched_and_no_requirements_silent():
    rows, un = refine_requirements(env("app_details", {"steam_appid": 9, "data": {}}), {}.get)
    assert rows == [] and un[0]["key"] == 9
    rows, un = refine_requirements(
        env("app_details", {"steam_appid": 7, "data": {"pc_requirements": []}}), {7: 1}.get
    )
    assert rows == [] and un == []


# ---- danawa ----
def con(**kw):
    p = {
        "pcode": "1",
        "product_name": "SONY PS5 엘든 링 한글판 (초회한정)",
        "platform_hint": "PS5",
        "edition": "physical",
        "lowest_price": 52000,
        "url": "u",
    }
    p.update(kw)
    return env("console_price", p)


def test_console_price_new_only_and_filters():
    rows, un = refine_console_price(con(), {"엘든 링": 119133}.get)
    assert un == [] and rows[0]["store"] == "danawa" and rows[0]["price_krw"] == 52000
    assert rows[0]["currency_original"] == "KRW" and rows[0]["edition"] == "physical"
    assert (
        refine_console_price(con(product_name="[호환] 닌텐도 엘든 링"), {}.get)[1][0]["reason"]
        == "해외판·호환판 표기"
    )
    assert "중고" in refine_console_price(con(condition="used"), {"엘든 링": 1}.get)[1][0]["reason"]
    assert refine_console_price(con(lowest_price=None), {}.get)[1][0]["reason"] == "가격 없음"
    assert "매칭 실패" in refine_console_price(con(), {}.get)[1][0]["reason"]


def test_infer_edition():
    assert (
        infer_edition(
            {"edition": None, "product_name": "엘든 링 스팀 코드", "platform_hint": "PS5"}
        )
        == "code"
    )
    assert (
        infer_edition({"edition": None, "product_name": "엘든 링", "platform_hint": "PS5"})
        == "physical"
    )
    assert (
        infer_edition({"edition": None, "product_name": "엘든 링", "platform_hint": "PC"}) == "code"
    )


# ---- router ----
def test_router_routes_by_kind_and_ignores_unknown():
    maps = Maps({"itad": {"abc": 7}, "steam": {5: 7}, "alias": {"엘든 링": 7}})
    assert route(env("review", {}), maps)["ignored"] is True
    r = route(env("game_info", igdb_payload()), maps)
    assert [o[0] for o in r["out"]] == ["games"] and r["extras"]["platforms"]
    r = route(
        env("app_details", {"steam_appid": 5, "data": {"pc_requirements": {"minimum": HTML}}}), maps
    )
    assert [o[0] for o in r["out"]] == ["requirements"]
    r = route(
        env(
            "price",
            {
                "id": "abc",
                "deals": [
                    {
                        "shop": {"id": 61, "name": "Steam"},
                        "price": {"amount": 10, "currency": "KRW"},
                    }
                ],
            },
        ),
        maps,
    )
    assert [o[0] for o in r["out"]] == ["prices"]


def test_maps_accepts_old_flat_shape():
    assert Maps({"abc": "7"}).itad == {"abc": 7}


def test_example_file_matches_code_schema():
    path = Path(__file__).resolve().parents[2] / "docs/contracts/messages/refined.games.json"
    if not path.exists():
        pytest.skip("refined.games.json은 contracts PR(NW2-17)에서 추가된다")
    ex = json.loads(path.read_text(encoding="utf-8"))
    assert [f["field"] for f in ex["schema"]["fields"]] == [f for f, _, _ in REFINED_GAME_FIELDS]
    assert set(ex["payload"]) == {f for f, _, _ in REFINED_GAME_FIELDS}
