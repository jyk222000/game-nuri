#!/usr/bin/env python3
"""후보 풀(pool.csv) 만들기: IGDB → Steam → ITAD 순으로 붙인다.

응답 필드 이름은 docs/collector-test/*.md 와 docs/contracts/messages/raw.igdb.json 기준이다.
처음엔 --limit 20 으로 돌려 pool.csv 와 캐시를 눈으로 확인한 뒤 전체를 돌린다.

키는 .env 에서만 읽는다 (TWITCH_CLIENT_ID, TWITCH_CLIENT_SECRET, ITAD_KEY). 출력에 키를 찍지 않는다.
결과물은 analysis/data/game_pool/ 아래에 저장된다 (analysis/data/ 는 Git 제외).
Steam 과 ITAD 처럼 호출이 많은 단계는 게임마다 캐시에 저장하므로 중단해도 이어 돌릴 수 있다.

사용:  python analysis/scripts/build_pool.py --pool-size 4000 [--limit 20]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "analysis" / "data" / "game_pool"
CACHE = DATA / ".cache"
UA = "gamenuri-pool-builder/0.1"
PLATFORM_IDS = {6: "PC", 167: "PS5", 48: "PS4", 130: "Switch", 508: "Switch2",
                169: "XboxSeries", 49: "XboxOne"}
ONLINE_MODES = {2, 3, 5, 6}        # IGDB game_modes: multiplayer, co-op, MMO, battle royale
EROTIC_THEME = 42                  # IGDB themes: Erotic
STEAM_SHOP_ID = 61                 # ITAD shops: Steam
MIN_KO_REVIEWS = 200               # select_games.py 의 MIN_KO_REVIEWS 와 같은 값으로 맞춘다
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
HANGUL = re.compile(r"[가-힣]")


def cached(name: str, fn):
    CACHE.mkdir(parents=True, exist_ok=True)
    p = CACHE / f"{name}.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    v = fn()
    p.write_text(json.dumps(v, ensure_ascii=False), encoding="utf-8")
    return v


def cached_map(name: str, keys: list[str], fn, save_every: int = 25) -> dict:
    """키마다 fn(key) 결과를 캐시에 쌓는다. 중단돼도 지금까지 받은 것은 남는다.
    fn 이 예외를 내면 그 키는 저장하지 않고(다음 실행에서 재시도) 건너뛴다."""
    CACHE.mkdir(parents=True, exist_ok=True)
    p = CACHE / f"{name}.json"
    data: dict = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    todo = [k for k in keys if k not in data]
    failed = 0
    try:
        for i, k in enumerate(todo, 1):
            try:
                data[k] = fn(k)
            except Exception as e:  # noqa: BLE001  키가 섞인 URL 을 찍지 않도록 메시지는 get() 이 정리한다
                failed += 1
                print(f"  [{name}] {k} 실패: {e}")
            if i % save_every == 0:
                p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
                print(f"  [{name}] {i}/{len(todo)}")
    finally:
        p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    if failed:
        print(f"  [{name}] 실패 {failed}건 → 다시 실행하면 이 건들만 재시도한다")
    return data


def get(url, retries=5, **kw):
    """GET + 429/5xx 지수 백오프. 오류 메시지에는 쿼리(키)를 넣지 않는다."""
    base = url.split("?")[0]
    for i in range(retries):
        r = requests.get(url, timeout=30, headers={"User-Agent": UA}, **kw)
        if r.status_code in (429, 500, 502, 503, 504):
            time.sleep(float(r.headers.get("Retry-After", 2 ** (i + 1))))
            continue
        if not r.ok:
            raise RuntimeError(f"HTTP {r.status_code}: {base}")
        return r.json()
    raise RuntimeError(f"재시도 초과: {base}")


# ------------------------------------------------------------------ IGDB
class Igdb:
    def __init__(self):
        r = requests.post("https://id.twitch.tv/oauth2/token", timeout=30, data=dict(
            client_id=os.environ["TWITCH_CLIENT_ID"], client_secret=os.environ["TWITCH_CLIENT_SECRET"],
            grant_type="client_credentials"))
        if not r.ok:
            raise RuntimeError(f"Twitch 토큰 발급 실패: HTTP {r.status_code}")
        self.h = {"Client-ID": os.environ["TWITCH_CLIENT_ID"],
                  "Authorization": f"Bearer {r.json()['access_token']}"}

    def q(self, endpoint, body):
        for i in range(4):
            r = requests.post(f"https://api.igdb.com/v4/{endpoint}", headers=self.h,
                              data=body.encode("utf-8"), timeout=30)
            if r.status_code == 429:
                time.sleep(2 ** (i + 1))
                continue
            if not r.ok:
                raise RuntimeError(f"IGDB {endpoint} HTTP {r.status_code}: {r.text[:200]}")
            time.sleep(0.3)                      # 초당 4회 한도
            return r.json()
        raise RuntimeError("IGDB 재시도 초과")


FIELDS = ("name,slug,game_type,first_release_date,total_rating_count,aggregated_rating,"
          "aggregated_rating_count,platforms,genres.name,game_modes,themes,collections.id,"
          "collections.name,involved_companies.publisher,involved_companies.developer,"
          "involved_companies.company.name,external_games.external_game_source,external_games.uid,"
          "release_dates.date,release_dates.platform,game_localizations.name,"
          "game_localizations.region.name")


def igdb_pool(ig: Igdb, size: int, limit: int | None) -> list[dict]:
    """IGDB 평가 수 상위부터 size건. Steam 외부 ID 없는 건 나중에 거른다."""
    out, offset = [], 0
    while len(out) < size:
        page = ig.q("games", f"fields {FIELDS}; where total_rating_count > 10 & "
                             f"first_release_date != null; sort total_rating_count desc; "
                             f"limit 500; offset {offset};")
        if not page:
            break
        out += page
        offset += 500
        if limit and len(out) >= limit:
            break
    return out[: (limit or size)]


def igdb_ttb(ig: Igdb, ids: list[int]) -> dict[int, dict]:
    res = {}
    for i in range(0, len(ids), 500):
        chunk = ids[i:i + 500]
        for row in ig.q("game_time_to_beats",
                        f"fields game_id,hastily,normally,completely,count; "
                        f"where game_id = ({','.join(map(str, chunk))}); limit 500;"):
            res[row["game_id"]] = row
    return res


def flatten_igdb(g: dict) -> dict:
    # uid 가 "292030,378649,378648"처럼 여러 appid 를 쉼표로 묶어 오는 게임이 있다 → 첫 값(본편) 사용
    steam = next((str(e["uid"]).split(",")[0].strip() for e in g.get("external_games", [])
                  if e.get("external_game_source") == 1
                  and str(e.get("uid", "")).split(",")[0].strip().isdigit()), None)
    plats = [PLATFORM_IDS[p] for p in g.get("platforms", []) if p in PLATFORM_IDS]
    comps = g.get("involved_companies", [])
    pub = next((c["company"]["name"] for c in comps
                if c.get("publisher") and c.get("company", {}).get("name")), None)
    dev = next((c["company"]["name"] for c in comps
                if c.get("developer") and c.get("company", {}).get("name")), None)
    col = (g.get("collections") or [{}])[0]
    ko = next((loc["name"] for loc in g.get("game_localizations", [])
               if loc.get("name") and "korea" in (loc.get("region", {}).get("name", "")).lower()),
              None)
    pc_dates = [d["date"] for d in g.get("release_dates", [])
                if d.get("platform") == 6 and d.get("date")]
    con_dates = [d["date"] for d in g.get("release_dates", [])
                 if PLATFORM_IDS.get(d.get("platform")) not in (None, "PC") and d.get("date")]

    def ts(v):
        # fromtimestamp 는 Windows 에서 1970년 이전(음수) 값을 못 읽으므로 epoch 에 더한다
        return (EPOCH + timedelta(seconds=v)).date().isoformat() if v else None

    return dict(
        game_id=g["id"], name=g.get("name"), name_ko=ko, steam_appid=steam,
        game_type=g.get("game_type", 0),
        release_date=ts(g.get("first_release_date")), rating_count=g.get("total_rating_count"),
        aggregated_rating=g.get("aggregated_rating"),
        aggregated_rating_count=g.get("aggregated_rating_count", 0),
        platforms="|".join(plats), genres="|".join(x["name"] for x in g.get("genres", []) if x.get("name")),
        publisher=pub, developer=dev, series_id=str(col["id"]) if col.get("id") else None,
        series_name=col.get("name"), is_online=bool(set(g.get("game_modes", [])) & ONLINE_MODES),
        is_adult=EROTIC_THEME in g.get("themes", []),
        pc_release_date=ts(min(pc_dates)) if pc_dates else None,
        console_first_release_date=ts(min(con_dates)) if con_dates else None)


# ------------------------------------------------------------------ Steam (키 불필요)
def steam_reviews(appids: list[str]) -> dict[str, dict]:
    """GetItems 로 한국어 리뷰 수·긍정률·무료 여부. 100개씩. Steam 구매 기준(steam-notes 2절)."""
    res = {}
    for i in range(0, len(appids), 100):
        inp = json.dumps(dict(ids=[{"appid": int(a)} for a in appids[i:i + 100]],
                              context=dict(language="koreana", country_code="KR"),
                              data_request=dict(include_reviews=True)))
        data = get("https://api.steampowered.com/IStoreBrowseService/GetItems/v1/",
                   params={"input_json": inp})
        for it in data.get("response", {}).get("store_items", []):
            s = (it.get("reviews") or {}).get("summary_language_specific") or {}
            res[str(it.get("appid"))] = dict(
                review_count_ko=int(s.get("review_count", 0) or 0),
                positive_pct_ko=float(s.get("percent_positive", 0) or 0),
                is_free=bool(it.get("is_free")),
                has_kr_price=bool(it.get("best_purchase_option")) or bool(it.get("is_free")),
                name_steam_ko=it.get("name"))
        print(f"  [steam] {min(i + 100, len(appids))}/{len(appids)}")
        time.sleep(1.5)
    return res


def steam_ccu(appid: str) -> int | None:
    d = get("https://api.steampowered.com/ISteamUserStats/GetNumberOfCurrentPlayers/v1/",
            params={"appid": appid})
    return d["response"].get("player_count")


# ------------------------------------------------------------------ ITAD
def itad_history(appid: str) -> dict:
    """lookup → history. 할인 이벤트 = Steam 가격 변동에서 cut 이 0 → 양수로 바뀐 횟수 (최근 24개월)."""
    key = os.environ["ITAD_KEY"]
    base = "https://api.isthereanydeal.com"
    lk = get(f"{base}/games/lookup/v1", params={"key": key, "appid": appid})  # app/ 접두사 금지
    if not lk.get("found"):
        return dict(itad_id=None)
    gid = lk["game"]["id"]
    time.sleep(0.3)
    hist = get(f"{base}/games/history/v2",
               params={"key": key, "id": gid, "country": "KR", "shops": STEAM_SHOP_ID,
                       "since": "2000-01-01T00:00:00Z"})  # since 없으면 최근 약 3개월만 온다
    ev = sorted(hist, key=lambda e: e["timestamp"])
    time.sleep(0.3)
    if not ev:
        return dict(itad_id=gid, discount_events_24m=0, history_months=0)

    def t(e):
        return datetime.fromisoformat(e["timestamp"].replace("Z", "+00:00"))

    now = datetime.now(timezone.utc)
    events, prev_cut = 0, 0
    for e in ev:
        cut = (e.get("deal") or {}).get("cut", 0) or 0
        if cut > 0 and prev_cut == 0 and (now - t(e)).days <= 730:
            events += 1
        prev_cut = cut
    return dict(itad_id=gid, discount_events_24m=events,
                history_months=int((now - t(ev[0])).days / 30))


# ------------------------------------------------------------------ main
def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # Windows 콘솔(cp949) 출력 오류 방지
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=DATA / "pool.csv")
    ap.add_argument("--pool-size", type=int, default=4000)
    ap.add_argument("--limit", type=int, help="시험용: 이 건수만")
    a = ap.parse_args()
    load_dotenv(REPO / ".env")
    DATA.mkdir(parents=True, exist_ok=True)
    tag = f"_{a.limit}" if a.limit else ""

    ig = Igdb()
    raw = cached(f"igdb{tag}", lambda: igdb_pool(ig, a.pool_size, a.limit))
    rows = [flatten_igdb(g) for g in raw]
    rows = [r for r in rows if r["steam_appid"]]                    # ID 통합 불가는 여기서 제외
    seen: set[str] = set()                                           # 같은 appid 는 평가 수 많은 쪽만
    rows = [r for r in rows if not (r["steam_appid"] in seen or seen.add(r["steam_appid"]))]
    print(f"IGDB {len(raw)}건 중 Steam ID 있는 {len(rows)}건(appid 중복 제거 후)")

    ttb = cached(f"ttb{tag}", lambda: {str(k): v for k, v in
                                       igdb_ttb(ig, [r["game_id"] for r in rows]).items()})
    for r in rows:
        t = ttb.get(str(r["game_id"]), {})
        r["ttb_normally_sec"], r["ttb_count"] = t.get("normally"), t.get("count")

    stm = cached(f"steam{tag}", lambda: steam_reviews([r["steam_appid"] for r in rows]))
    rows = [{**r, **stm[r["steam_appid"]]} for r in rows if r["steam_appid"] in stm]
    # 한국어 리뷰 최소 미만은 어차피 탈락하므로 ITAD 호출 전에 줄인다 (호출 수 절감).
    # 200건 미만은 Steam GetItems 가 요약을 0으로 주므로 200이 측정 가능한 하한이다.
    rows = [r for r in rows if r["review_count_ko"] >= MIN_KO_REVIEWS]
    print(f"한국어 리뷰 {MIN_KO_REVIEWS}건 이상 {len(rows)}건")

    # 한글 검색어(A2·다나와 매칭): IGDB 한국 현지명이 없으면 Steam 한국어 상점명이 한글일 때 대체
    for r in rows:
        if not r["name_ko"] and r.get("name_steam_ko") and HANGUL.search(r["name_steam_ko"]):
            r["name_ko"] = r["name_steam_ko"]

    appids = [r["steam_appid"] for r in rows]
    ccu = cached_map(f"ccu{tag}", appids, steam_ccu)
    itad = cached_map(f"itad{tag}", appids, itad_history)
    for r in rows:
        r["ccu_peak"] = ccu.get(r["steam_appid"])           # 현재 접속자 스냅샷 (최고치 아님, 근사)
        r.update(itad.get(r["steam_appid"], {}))
    pd.DataFrame(rows).to_csv(a.out, index=False, encoding="utf-8-sig")
    print(f"→ {a.out} ({len(rows)}건)")


if __name__ == "__main__":
    main()
