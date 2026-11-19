"""
겜누리 - API 동작 확인 스크립트

사용법
  1) pip install requests python-dotenv
  2) 같은 폴더에 .env 파일을 만들고 키를 넣는다 (아래 예시)
  3) python api_check.py            # 전체 확인
     python api_check.py itad igdb  # 일부만 확인

.env 예시 (키가 없는 항목은 비워 두면 건너뜀)
  ITAD_KEY=...
  TWITCH_CLIENT_ID=...
  TWITCH_CLIENT_SECRET=...
  STEAM_KEY=...
  STEAM_ID=7656119xxxxxxxxxx      # 게임 정보가 '공개'인 SteamID64
"""

import json
import os
import sys
import time
import urllib.robotparser
from urllib.parse import quote

import requests

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

TEST_APPID = 1245620  # 테스트용 Steam 게임 (ELDEN RING)
TEST_TITLE = "Elden Ring"
DANAWA_QUERY = "엘든링 PS5"
UA = {"User-Agent": "Mozilla/5.0 (game-nuri student project API check)"}
TIMEOUT = 15

results = []


def report(name, ok, detail=""):
    mark = "OK  " if ok else "FAIL"
    results.append((name, ok))
    print(f"[{mark}] {name}")
    if detail:
        for line in str(detail).splitlines():
            print(f"        {line}")


def short(obj, n=400):
    s = json.dumps(obj, ensure_ascii=False) if not isinstance(obj, str) else obj
    return s[:n] + (" ..." if len(s) > n else "")


# ---------------------------------------------------------------- ITAD
def check_itad():
    key = os.getenv("ITAD_KEY")
    if not key:
        report("ITAD", False, "ITAD_KEY 없음 → isthereanydeal.com 에서 앱 등록 후 키 발급")
        return
    base = "https://api.isthereanydeal.com"
    # 1) 게임 찾기 (Steam appid 로)
    r = requests.get(
        f"{base}/games/lookup/v1", params={"key": key, "appid": TEST_APPID}, timeout=TIMEOUT
    )
    if r.status_code != 200 or not r.json().get("found"):
        report("ITAD 게임 찾기", False, f"HTTP {r.status_code}: {short(r.text)}")
        return
    game = r.json()["game"]
    report("ITAD 게임 찾기", True, f"{game['title']} → ITAD id {game['id']}")

    # 2) 현재 가격 (한국 기준)
    r = requests.post(
        f"{base}/games/prices/v3",
        params={"key": key, "country": "KR"},
        json=[game["id"]],
        timeout=TIMEOUT,
    )
    if r.status_code != 200:
        report("ITAD 현재 가격", False, f"HTTP {r.status_code}: {short(r.text)}")
    else:
        deals = (r.json() or [{}])[0].get("deals", [])
        lines = [
            f"{d['shop']['name']}: {d['price']['amount']} {d['price']['currency']} "
            f"(정가 {d['regular']['amount']}, -{d['cut']}%)"
            for d in deals[:8]
        ]
        report("ITAD 현재 가격 (KR)", bool(deals), "\n".join(lines) or "스토어 가격 없음")

    # 3) 역대 최저가
    r = requests.post(
        f"{base}/games/historylow/v1",
        params={"key": key, "country": "KR"},
        json=[game["id"]],
        timeout=TIMEOUT,
    )
    report("ITAD 역대 최저가", r.status_code == 200, f"HTTP {r.status_code}: {short(r.text, 300)}")


# ---------------------------------------------------------------- IGDB
def check_igdb():
    cid, secret = os.getenv("TWITCH_CLIENT_ID"), os.getenv("TWITCH_CLIENT_SECRET")
    if not (cid and secret):
        report(
            "IGDB",
            False,
            "TWITCH_CLIENT_ID / TWITCH_CLIENT_SECRET 없음 → dev.twitch.tv/console 에서 앱 등록",
        )
        return
    r = requests.post(
        "https://id.twitch.tv/oauth2/token",
        params={"client_id": cid, "client_secret": secret, "grant_type": "client_credentials"},
        timeout=TIMEOUT,
    )
    if r.status_code != 200:
        report("IGDB 토큰 발급", False, f"HTTP {r.status_code}: {short(r.text)}")
        return
    token = r.json()["access_token"]
    report("IGDB 토큰 발급", True, f"만료까지 {r.json().get('expires_in')}초")

    headers = {"Client-ID": cid, "Authorization": f"Bearer {token}"}
    body = (
        f'search "{TEST_TITLE}"; '
        "fields name, first_release_date, genres.name, platforms.name, "
        "external_games.uid, external_games.external_game_source; limit 3;"
    )
    r = requests.post("https://api.igdb.com/v4/games", headers=headers, data=body, timeout=TIMEOUT)
    if r.status_code != 200:
        report("IGDB 게임 검색", False, f"HTTP {r.status_code}: {short(r.text)}")
        return
    lines = []
    for g in r.json():
        ext = [
            f"src{e.get('external_game_source')}:{e.get('uid')}"
            for e in g.get("external_games", [])[:6]
        ]
        lines.append(f"{g['name']} (id {g['id']}) 외부ID {', '.join(ext)}")
    report("IGDB 게임 검색", bool(lines), "\n".join(lines))
    time.sleep(0.3)  # 초당 4회 제한


# ---------------------------------------------------------------- Steam (키 필요 없음)
def check_steam_store():
    r = requests.get(
        "https://store.steampowered.com/api/appdetails",
        params={"appids": TEST_APPID, "cc": "kr", "l": "korean"},
        headers=UA,
        timeout=TIMEOUT,
    )
    data = r.json().get(str(TEST_APPID), {}) if r.status_code == 200 else {}
    if data.get("success"):
        d = data["data"]
        price = d.get("price_overview", {}).get("final_formatted", "가격 정보 없음")
        report("Steam 스토어 상세 (키 불필요)", True, f"{d['name']} / {price}")
    else:
        report("Steam 스토어 상세 (키 불필요)", False, f"HTTP {r.status_code}")


def check_steam_reviews():
    r = requests.get(
        f"https://store.steampowered.com/appreviews/{TEST_APPID}",
        params={"json": 1, "language": "koreana", "num_per_page": 3, "filter": "recent"},
        headers=UA,
        timeout=TIMEOUT,
    )
    ok = r.status_code == 200 and r.json().get("success") == 1
    if ok:
        j = r.json()
        s = j.get("query_summary", {})
        first = (j.get("reviews") or [{}])[0].get("review", "")[:80].replace("\n", " ")
        report(
            "Steam 리뷰 API (키 불필요)",
            True,
            f"요약: {s.get('review_score_desc')} / 받은 리뷰 {s.get('num_reviews')}건\n예: {first}",
        )
    else:
        report("Steam 리뷰 API (키 불필요)", False, f"HTTP {r.status_code}")


# ---------------------------------------------------------------- Steam Web API (키 필요)
def check_steam_web():
    key, sid = os.getenv("STEAM_KEY"), os.getenv("STEAM_ID")
    if not (key and sid):
        report(
            "Steam Web API",
            False,
            "STEAM_KEY / STEAM_ID 없음 → steamcommunity.com/dev/apikey 에서 키 발급",
        )
        return
    r = requests.get(
        "https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/",
        params={"key": key, "steamids": sid},
        timeout=TIMEOUT,
    )
    players = r.json().get("response", {}).get("players", []) if r.status_code == 200 else []
    report(
        "Steam 프로필",
        bool(players),
        f"{players[0].get('personaname')} (공개 상태 {players[0].get('communityvisibilitystate')}, 3=공개)"
        if players
        else f"HTTP {r.status_code}: {short(r.text)}",
    )

    r = requests.get(
        "https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/",
        params={"key": key, "steamid": sid, "include_appinfo": 1, "format": "json"},
        timeout=TIMEOUT,
    )
    resp = r.json().get("response", {}) if r.status_code == 200 else {}
    games = sorted(resp.get("games", []), key=lambda g: -g.get("playtime_forever", 0))[:3]
    report(
        "Steam 보유 게임",
        "game_count" in resp,
        f"보유 {resp.get('game_count', '?')}개, 많이 한 게임: "
        + ", ".join(f"{g.get('name')} {g.get('playtime_forever', 0) // 60}시간" for g in games)
        if resp
        else "응답이 비어 있음 → 프로필의 '게임 세부 정보'가 비공개일 가능성",
    )


# ---------------------------------------------------------------- 다나와
def check_danawa():
    url = f"https://search.danawa.com/dsearch.php?query={quote(DANAWA_QUERY)}"
    rp = urllib.robotparser.RobotFileParser()
    rp.set_url("https://search.danawa.com/robots.txt")
    try:
        rp.read()
        allowed = rp.can_fetch(UA["User-Agent"], url)
        report(
            "다나와 robots.txt",
            allowed,
            "검색 페이지 수집 허용"
            if allowed
            else "robots.txt 가 이 경로를 막고 있음 → 약관 검토 필요",
        )
    except Exception as e:
        report("다나와 robots.txt", False, f"읽기 실패: {e}")

    r = requests.get(url, headers=UA, timeout=TIMEOUT)
    hits = r.text.count("prod_name")
    report(
        "다나와 검색 페이지",
        r.status_code == 200 and hits > 0,
        f"HTTP {r.status_code}, 상품명 영역 {hits}곳 발견"
        + (
            ""
            if hits
            else "\n상품이 HTML에 없으면 JS로 불러오는 구조일 수 있음 → 개발자도구 Network 탭 확인"
        ),
    )


# ---------------------------------------------------------------- 환율
def check_fx():
    r = requests.get(
        "https://api.frankfurter.app/latest", params={"from": "USD", "to": "KRW"}, timeout=TIMEOUT
    )
    ok = r.status_code == 200 and "KRW" in r.json().get("rates", {})
    report(
        "환율 (USD→KRW, 키 불필요)",
        ok,
        f"1 USD = {r.json()['rates']['KRW']} KRW ({r.json().get('date')})"
        if ok
        else f"HTTP {r.status_code}",
    )


CHECKS = {
    "itad": check_itad,
    "igdb": check_igdb,
    "steamstore": check_steam_store,
    "reviews": check_steam_reviews,
    "steamweb": check_steam_web,
    "danawa": check_danawa,
    "fx": check_fx,
}

if __name__ == "__main__":
    names = sys.argv[1:] or list(CHECKS)
    for n in names:
        print(f"\n=== {n} ===")
        try:
            CHECKS[n]()
        except Exception as e:
            report(n, False, f"예외 발생: {type(e).__name__}: {e}")
    print("\n=== 요약 ===")
    for name, ok in results:
        print(f"{'OK  ' if ok else 'FAIL'}  {name}")
