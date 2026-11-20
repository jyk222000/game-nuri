# ruff: noqa  -- 수집 가능성 시험용 일회성 스크립트(NW2-83). 운영 코드 아님
"""Steam 개인 데이터(명세 ④) 수집 가능 여부 확인.
입력: vanity ID (예: 본인 Steam 커스텀 URL 이름). 키는 .env 의 STEAM_API_KEY 에서만 읽는다.
저장: samples/check_steam_user/ (원본 JSON 그대로, 키 값은 저장하지 않음)
"""

import json
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
KEY = os.environ.get("STEAM_API_KEY")
OUT = ROOT / "samples" / "check_steam_user"
OUT.mkdir(parents=True, exist_ok=True)
API = "https://api.steampowered.com"


def call(name, path, **params):
    params["key"] = KEY
    time.sleep(0.3)
    r = requests.get(f"{API}/{path}", params=params, timeout=30)
    try:
        j = r.json()
    except ValueError:
        j = {"_error": f"JSON 아님 (HTTP {r.status_code})"}
    (OUT / f"{name}.json").write_text(json.dumps(j, ensure_ascii=False, indent=1), encoding="utf-8")
    return r.status_code, j


def main():
    if not KEY:
        sys.exit("STEAM_API_KEY 없음 (.env 확인)")
    vanity = sys.argv[1]
    sc, j = call("01_resolve_vanity", "ISteamUser/ResolveVanityURL/v1/", vanityurl=vanity)
    resp = j.get("response", {})
    print("ResolveVanityURL:", sc, "success=", resp.get("success"), resp.get("message", ""))
    sid = resp.get("steamid")
    if not sid:
        # 숫자 SteamID64 를 직접 준 경우 대비
        if vanity.isdigit():
            sid = vanity
        else:
            return
    sc, j = call("02_player_summary", "ISteamUser/GetPlayerSummaries/v2/", steamids=sid)
    pl = (j.get("response", {}).get("players") or [{}])[0]
    print(
        "GetPlayerSummaries:",
        sc,
        "visibility=",
        pl.get("communityvisibilitystate"),
        "(3=공개)",
        "필드:",
        sorted(pl.keys()),
    )
    sc, j = call(
        "03_owned_games",
        "IPlayerService/GetOwnedGames/v1/",
        steamid=sid,
        include_appinfo=1,
        include_played_free_games=1,
    )
    r = j.get("response", {})
    games = r.get("games", [])
    print(
        "GetOwnedGames:",
        sc,
        "game_count=",
        r.get("game_count"),
        "받은 목록=",
        len(games),
        "필드:",
        sorted(games[0].keys()) if games else "(비어 있음: 비공개이거나 게임 없음)",
    )
    sc, j = call("04_recent_games", "IPlayerService/GetRecentlyPlayedGames/v1/", steamid=sid)
    r = j.get("response", {})
    print("GetRecentlyPlayedGames:", sc, "total_count=", r.get("total_count"))
    sc, j = call("05_steam_level", "IPlayerService/GetSteamLevel/v1/", steamid=sid)
    print("GetSteamLevel:", sc, j.get("response"))
    # 업적: 가장 많이 플레이한 게임 1개
    if games:
        top = max(games, key=lambda g: g.get("playtime_forever", 0))
        print("플레이 최다:", top.get("name"), top.get("appid"), top.get("playtime_forever"), "분")
        sc, j = call(
            "06_achievements_top",
            "ISteamUserStats/GetPlayerAchievements/v1/",
            steamid=sid,
            appid=top["appid"],
            l="koreana",
        )
        ps = j.get("playerstats", {})
        ach = ps.get("achievements", [])
        print(
            "GetPlayerAchievements:",
            sc,
            "success=",
            ps.get("success"),
            ps.get("error", ""),
            "업적 수=",
            len(ach),
            "달성=",
            sum(1 for a in ach if a.get("achieved")),
        )
    sc, j = call("07_friends", "ISteamUser/GetFriendList/v1/", steamid=sid, relationship="friend")
    print(
        "GetFriendList:",
        sc,
        "친구 수=",
        len(j.get("friendslist", {}).get("friends", [])) if isinstance(j, dict) else "",
    )


if __name__ == "__main__":
    main()
