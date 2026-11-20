# ruff: noqa  -- 수집 가능성 시험용 일회성 스크립트(NW2-83). 운영 코드 아님
"""명세 대비 부족했던 수집 항목 확인 (ITAD 가격/최저가/통화, IGDB 확장 필드, Steam 동접·업적).

대상은 check_candidates 결과(samples/check_candidates/result.json)에서 고른 후보 3개.
원본 응답은 samples/check_gaps/ 에 그대로 저장하고, 호출별 성공 여부·핵심 필드를 요약해 출력한다.
키는 .env 에서만 읽고 출력·저장에서 마스킹한다. 호출 한도는 check_candidates 와 같은 게이트를 쓴다.

Steam 보유 게임·플레이타임·업적(개인 데이터)은 SteamID(공개 프로필)가 필요해서 이 스크립트에서 제외했다.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

import check_candidates as cc  # 같은 폴더의 http/Throttle/Igdb/redact/save_json 재사용

OUT = cc.ROOT / "samples" / "check_gaps"
TARGETS = [
    "엘든 링",
    "바이오하자드 4",
    "몬스터 헌터 월드",
]  # 에디션·리메이크·확장팩 관계가 있는 후보
ITAD = "https://api.isthereanydeal.com"

IGDB_FIELDS_FULL = (
    "name,slug,summary,first_release_date,game_type.type,"
    "genres.name,themes.name,game_modes.name,player_perspectives.name,keywords.name,"
    "cover.url,cover.image_id,screenshots.image_id,"
    "parent_game.name,version_parent.name,dlcs.name,expansions.name,standalone_expansions.name,"
    "remakes.name,remasters.name,bundles.name,similar_games.name,"
    "involved_companies.company.name,involved_companies.developer,involved_companies.publisher,"
    "release_dates.date,release_dates.human,release_dates.region,release_dates.platform.name,"
    "websites.url,websites.type,age_ratings.rating,age_ratings.organization,"
    "total_rating,total_rating_count,aggregated_rating,rating"
)

summary: dict = {}


def step(name: str, fn):
    """호출 하나를 실행하고 성공/실패를 요약에 기록한다. 실패해도 다음 호출로 넘어간다."""
    try:
        res = fn()
        summary[name] = res
        print(f"  OK   {name}: {json.dumps(res, ensure_ascii=False)[:230]}")
    except Exception as e:  # noqa: BLE001
        summary[name] = {"_error": cc.redact(e)[:300]}
        print(f"  FAIL {name}: {cc.redact(e)[:300]}")


def keys_of(obj, depth=1):
    if isinstance(obj, dict):
        return sorted(obj.keys()) if depth else "dict"
    if isinstance(obj, list):
        return f"list[{len(obj)}]"
    return type(obj).__name__


def itad_calls(key: str, g: dict, slug: str):
    iid = g["itad_id"]
    common = {"key": key, "country": "KR"}

    def post(path, extra=None):
        r = cc.http(
            "POST", f"{ITAD}{path}", cc.itad_gate, params={**common, **(extra or {})}, json=[iid]
        )
        cc.save_json(
            OUT / "itad" / f"{slug}_{path.strip('/').replace('/', '_')}.json",
            r.json()
            if r.headers.get("content-type", "").startswith("application/json")
            else r.text[:500],
        )
        if r.status_code != 200:
            raise RuntimeError(f"HTTP {r.status_code} {cc.redact(r.text[:150])}")
        return r.json()

    def prices():
        j = post("/games/prices/v3", {"deals": "false", "vouchers": "false"})
        deals = j[0].get("deals", []) if j else []
        first = deals[0] if deals else {}
        return {
            "shops": len(deals),
            "currency": (first.get("price") or {}).get("currency"),
            "sample": {
                k: first.get(k) for k in ("shop", "price", "regular", "cut", "drm", "storeLow")
            },
            "keys": sorted(j[0].keys()) if j else None,
            "historyLow_key": (j[0] or {}).get("historyLow") if j else None,
        }

    def overview():
        j = post("/games/overview/v2")
        return {
            "keys": sorted(j.keys()) if isinstance(j, dict) else keys_of(j),
            "current": (j.get("prices") or [{}])[0]
            if isinstance(j, dict) and j.get("prices")
            else None,
            "lows": (j.get("prices") or [{}])[0].get("lows")
            if isinstance(j, dict) and j.get("prices")
            else None,
        }

    def historylow():
        j = post("/games/historylow/v1")
        return {"raw": j[:1] if isinstance(j, list) else j}

    def info():
        r = cc.http("GET", f"{ITAD}/games/info/v2", cc.itad_gate, params={"key": key, "id": iid})
        cc.save_json(
            OUT / "itad" / f"{slug}_games_info_v2.json",
            r.json() if r.status_code == 200 else r.text[:300],
        )
        if r.status_code != 200:
            raise RuntimeError(f"HTTP {r.status_code}")
        j = r.json()
        return {
            "keys": sorted(j.keys()),
            "tags": (j.get("tags") or [])[:5],
            "reviews": j.get("reviews"),
            "players": j.get("players"),
            "stats": j.get("stats"),
        }

    step(f"{g['후보']}/ITAD prices(KR)", prices)
    step(f"{g['후보']}/ITAD overview(KR)", overview)
    step(f"{g['후보']}/ITAD historylow(KR)", historylow)
    step(f"{g['후보']}/ITAD info", info)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    load_dotenv(cc.ROOT / ".env")
    missing = [k for k in cc.REQUIRED_ENV if not os.getenv(k)]
    if missing:
        print(f".env 에 값이 없는 변수: {', '.join(missing)}")
        return 1
    cc._SECRETS.update(os.environ[k] for k in cc.REQUIRED_ENV)
    rows = json.loads((cc.OUT_DIR / "result.json").read_text(encoding="utf-8"))["rows"]
    games = [r for r in rows if r["후보"] in TARGETS]
    key = os.environ["ITAD_API_KEY"]

    print("== ITAD 공통 ==")

    def shops():
        r = cc.http("GET", f"{ITAD}/service/shops/v1", cc.itad_gate, params={"country": "KR"})
        j = r.json()
        cc.save_json(OUT / "itad" / "shops_KR.json", j)
        return {"count": len(j), "sample": j[:3]}

    step("ITAD shops(KR)", shops)

    def deals():
        r = cc.http(
            "GET",
            f"{ITAD}/deals/v2",
            cc.itad_gate,
            params={"key": key, "country": "KR", "limit": 5},
        )
        j = r.json()
        cc.save_json(OUT / "itad" / "deals_KR.json", j)
        if r.status_code != 200:
            raise RuntimeError(f"HTTP {r.status_code} {cc.redact(r.text[:150])}")
        first = (j.get("list") or [{}])[0]
        return {
            "keys": sorted(j.keys()),
            "count": len(j.get("list", [])),
            "currency": ((first.get("deal") or {}).get("price") or {}).get("currency"),
        }

    step("ITAD deals(KR)", deals)

    igdb = cc.Igdb(os.environ["IGDB_CLIENT_ID"], os.environ["IGDB_CLIENT_SECRET"])
    for g in games:
        slug = f"{g['igdb_id']}"
        print(f"\n== {g['후보']} (IGDB {g['igdb_id']}, appid {g['steam_appid']}) ==")
        itad_calls(key, g, slug)

        def igdb_ext():
            fields = IGDB_FIELDS_FULL
            for attempt in range(2):
                try:
                    j = igdb.query("games", f"fields {fields}; where id = {g['igdb_id']};")
                    break
                except RuntimeError as e:
                    if attempt:
                        raise
                    # 필드 하나가 거부되면 안전한 부분집합으로 재시도(어느 필드인지 요약에 남긴다)
                    summary.setdefault("igdb_field_errors", []).append(str(e)[:200])
                    fields = (
                        "name,summary,first_release_date,genres.name,themes.name,game_modes.name,"
                        "player_perspectives.name,cover.url,parent_game.name,version_parent.name,"
                        "dlcs.name,expansions.name,remakes.name,remasters.name,bundles.name,"
                        "involved_companies.company.name,involved_companies.developer,involved_companies.publisher,"
                        "release_dates.date,release_dates.region,release_dates.platform.name,total_rating,total_rating_count"
                    )
            cc.save_json(OUT / "igdb" / f"{slug}_games_ext.json", j)
            x = j[0] if j else {}
            return {
                "present": sorted(k for k, v in x.items() if v not in (None, [], "")),
                "genres": [a["name"] for a in x.get("genres", [])],
                "themes": [a["name"] for a in x.get("themes", [])],
                "cover": (x.get("cover") or {}).get("url"),
                "parent_game": (x.get("parent_game") or {}).get("name"),
                "version_parent": (x.get("version_parent") or {}).get("name"),
                "dlcs": len(x.get("dlcs", [])),
                "expansions": len(x.get("expansions", [])),
                "remakes": [a["name"] for a in x.get("remakes", [])],
                "remasters": [a["name"] for a in x.get("remasters", [])],
                "kr_release": [
                    d.get("date") for d in x.get("release_dates", []) if d.get("region") in (5, 8)
                ][:3],
            }

        step(f"{g['후보']}/IGDB 확장필드", igdb_ext)

        def igdb_ko():
            j = igdb.query(
                "game_localizations",
                f"fields name,region.name,cover.url; where game = {g['igdb_id']};",
            )
            cc.save_json(OUT / "igdb" / f"{slug}_localizations.json", j)
            return [
                {"name": a.get("name"), "region": (a.get("region") or {}).get("name")} for a in j
            ]

        step(f"{g['후보']}/IGDB 지역명", igdb_ko)

        appid = g["steam_appid"]

        def players():
            r = cc.http(
                "GET",
                "https://api.steampowered.com/ISteamUserStats/GetNumberOfCurrentPlayers/v1/",
                cc.steam_gate,
                params={"appid": appid},
            )
            cc.save_json(
                OUT / "steam" / f"{slug}_current_players.json",
                r.json() if r.status_code == 200 else r.text[:200],
            )
            if r.status_code != 200:
                raise RuntimeError(f"HTTP {r.status_code}")
            return r.json()

        step(f"{g['후보']}/Steam 현재 접속자", players)

        def ach():
            r = cc.http(
                "GET",
                "https://api.steampowered.com/ISteamUserStats/GetGlobalAchievementPercentagesForApp/v2/",
                cc.steam_gate,
                params={"gameid": appid},
            )
            if r.status_code != 200:
                raise RuntimeError(f"HTTP {r.status_code}")
            j = r.json()
            lst = (j.get("achievementpercentages") or {}).get("achievements", [])
            cc.save_json(OUT / "steam" / f"{slug}_achievement_percent.json", j)
            return {"count": len(lst), "sample": lst[:2]}

        step(f"{g['후보']}/Steam 업적 달성률", ach)

        def schema():
            r = cc.http(
                "GET",
                "https://api.steampowered.com/ISteamUserStats/GetSchemaForGame/v2/",
                cc.steam_gate,
                params={"key": os.environ["STEAM_API_KEY"], "appid": appid, "l": "koreana"},
            )
            if r.status_code != 200:
                raise RuntimeError(f"HTTP {r.status_code}")
            j = r.json()
            ach_l = ((j.get("game") or {}).get("availableGameStats") or {}).get("achievements", [])
            cc.save_json(OUT / "steam" / f"{slug}_schema.json", j)
            return {
                "achievements": len(ach_l),
                "sample": [
                    {"name": a.get("displayName"), "hidden": a.get("hidden")} for a in ach_l[:2]
                ],
            }

        step(f"{g['후보']}/Steam 업적 스키마(ko)", schema)

    cc.save_json(OUT / "summary.json", summary)
    print(f"\n저장 완료: {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
