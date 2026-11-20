# ruff: noqa  -- 수집 가능성 시험용 일회성 스크립트(NW2-83). 운영 코드 아님
"""후보 게임 15개의 수집 가능 여부 검증.

출처: IGDB / Steam / ITAD / 다나와
결과: samples/check_candidates/result.csv (+ 출처별 원본 샘플 JSON·HTML)

규칙(CLAUDE.md):
- 키는 .env 에서만 읽고, 출력/로그/저장물에 값이 남지 않게 한다.
- ITAD 5분 1,000회, IGDB 초당 4회(동시 8개), 다나와 3초 이상 + robots.txt 준수.
- 원본은 가공하지 않고 그대로 저장한다 (CSV 는 요약용).

사용법:  .venv/Scripts/python.exe scripts/check_candidates.py [--only 엘든] [--skip-danawa]
"""

from __future__ import annotations

import argparse
import csv
import html as htmllib
import json
import os
import re
import sys
import time
import urllib.robotparser
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "samples" / "check_candidates"
UA = "gamenuri-collect-test/0.1"

# ---------------------------------------------------------------- 후보
# ko: 한글 표기(다나와 검색), en: IGDB/ITAD 검색명, year: 동명 게임 구분용 출시연도(선택)
CANDIDATES = [
    {"ko": "엘든 링", "en": "Elden Ring", "danawa_exclude": r"밤의 통치자|nightreign"},
    {"ko": "사이버펑크 2077", "en": "Cyberpunk 2077"},
    {"ko": "위쳐 3", "en": "The Witcher 3: Wild Hunt"},
    {"ko": "레드 데드 리뎀션 2", "en": "Red Dead Redemption 2"},
    # 2018년작만: 후속작(라그나로크·발할라 등) 제외
    {
        "ko": "갓 오브 워",
        "en": "God of War",
        "year": 2018,
        "danawa_exclude": r"라그나로크|라우페이|발할라|ragnar|valhalla|3\b|III|콜렉션|collection|듀얼센스|컨트롤러|20주년",
    },
    # 리메이크(2023)만: 다나와 제목에 연도가 없어 PS4/PS5 구분이 어려움 → 결과의 note 확인 필요
    # 다나와 제목은 "바이오하자드 RE:4". 2005년판("바이오하자드4")과 섞이지 않게 이름을 직접 지정
    {
        "ko": "바이오하자드 4",
        "en": "Resident Evil 4",
        "year": 2023,
        "names": ["바이오하자드 RE:4", "바이오하자드 RE4"],
    },
    {"ko": "할로우 나이트", "en": "Hollow Knight", "danawa_exclude": r"실크\s*송|silksong"},
    {"ko": "몬스터 헌터 월드", "en": "Monster Hunter: World"},
    # aliases: 다나와 상품명 표기(저장된 검색 결과에서 확인). IGDB ko-KR 도 '헬다이버스 2' 로 동일.
    {"ko": "헬다이버즈 2", "en": "Helldivers 2", "aliases": ["헬다이버스 2"]},
    {"ko": "백 4 블러드", "en": "Back 4 Blood", "aliases": ["백 포 블러드"]},
    {"ko": "호그와트 레거시", "en": "Hogwarts Legacy"},
    {"ko": "스타듀 밸리", "en": "Stardew Valley", "aliases": ["스타듀벨리"]},
    {"ko": "잇 테이크스 투", "en": "It Takes Two", "aliases": ["잇 테이크 투"]},
    {"ko": "씨 오브 시브즈", "en": "Sea of Thieves"},
    {"ko": "하데스", "en": "Hades", "danawa_exclude": r"하데스\s*(2|II)|하데스2|Hades\s*(2|II)"},
]

REQUIRED_ENV = ["ITAD_API_KEY", "IGDB_CLIENT_ID", "IGDB_CLIENT_SECRET", "STEAM_API_KEY"]

# 플랫폼 판별 규칙 (앞에서부터 먼저 맞는 것). 입력: 번들명 → 카테고리 → 제목 순으로 시도.
PLATFORM_RULES = [
    ("Switch2", r"switch\s?2|스위치\s?2"),
    ("Switch", r"switch|스위치|닌텐도"),
    ("PS5", r"ps\s?5|플레이스테이션\s?5|플스\s?5"),
    ("PS4", r"ps\s?4|플레이스테이션\s?4|플스\s?4"),
    ("XboxSeries", r"(xbox|엑스박스)\s*(series|시리즈)|series\s*[xs]"),
    ("XboxOne", r"(xbox|엑스박스)\s*(one|원)|xbox\s*360"),
    ("Xbox", r"xbox|엑스박스"),  # 세대 표기 없음
    ("PC", r"(?<![a-z])pc(?![a-z])|pc게임|스팀|steam|gog|에픽|epic"),
]
CONSOLE_PLATFORMS = {"Switch2", "Switch", "PS5", "PS4", "XboxSeries", "XboxOne", "Xbox"}

_SECRETS: set[str] = set()


def redact(text: object) -> str:
    """로그에 키 값이 섞이지 않도록 마스킹."""
    s = str(text)
    for sec in _SECRETS:
        if sec:
            s = s.replace(sec, "***")
    return s


class Throttle:
    """호출 간 최소 간격 보장 (순차 호출이라 동시 접속 한도는 자동 충족)."""

    def __init__(self, min_interval: float):
        self.min_interval = min_interval
        self._last = 0.0

    def wait(self):
        gap = self.min_interval - (time.monotonic() - self._last)
        if gap > 0:
            time.sleep(gap)
        self._last = time.monotonic()


igdb_gate = Throttle(0.30)  # 초당 4회 한도 → 0.25초보다 여유 있게
itad_gate = Throttle(0.30)  # 5분 1,000회 한도 → 총 30회 내외라 충분
steam_gate = Throttle(1.5)  # appdetails 는 5분 200회 수준이라 보수적으로
danawa_gate = Throttle(10.0)  # 실행 시 robots.txt 의 Crawl-delay 로 갱신


def http(method: str, url: str, gate: Throttle, **kw) -> requests.Response:
    """요청 1회 + 429/5xx 시 1회 재시도. 예외 메시지는 마스킹해서 올린다."""
    kw.setdefault("timeout", 30)
    last_err = None
    for attempt in range(2):
        gate.wait()
        try:
            r = requests.request(method, url, **kw)
        except requests.RequestException as e:
            last_err = f"{type(e).__name__}: {redact(e)}"
            time.sleep(2)
            continue
        if r.status_code in (429, 500, 502, 503, 504) and attempt == 0:
            time.sleep(float(r.headers.get("Retry-After", 5)))
            last_err = f"HTTP {r.status_code}"
            continue
        return r
    raise RuntimeError(last_err or "request failed")


def save_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def norm(s: str) -> str:
    return re.sub(r"[^0-9a-z가-힣]", "", s.lower())


# ---------------------------------------------------------------- IGDB
class Igdb:
    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        r = http(
            "POST",
            "https://id.twitch.tv/oauth2/token",
            igdb_gate,
            params={
                "client_id": client_id,
                "client_secret": client_secret,
                "grant_type": "client_credentials",
            },
        )
        r.raise_for_status()
        token = r.json()["access_token"]
        _SECRETS.add(token)
        self.headers = {"Client-ID": client_id, "Authorization": f"Bearer {token}"}

    def query(self, endpoint: str, body: str):
        r = http(
            "POST",
            f"https://api.igdb.com/v4/{endpoint}",
            igdb_gate,
            headers=self.headers,
            data=body,
        )
        if r.status_code != 200:
            raise RuntimeError(f"IGDB {endpoint} HTTP {r.status_code}: {redact(r.text[:200])}")
        return r.json()

    def find_game(self, name: str, year: int | None):
        body = (
            f'search "{name}"; fields id,name,platforms.name,first_release_date,'
            f"total_rating_count; limit 20;"
        )
        results = self.query("games", body)
        exact = [g for g in results if norm(g.get("name", "")) == norm(name)]
        if year:
            exact = [
                g
                for g in exact
                if g.get("first_release_date")
                and datetime.fromtimestamp(g["first_release_date"], timezone.utc).year == year
            ]
        pool = exact or ([] if year else results)
        pick = max(pool, key=lambda g: g.get("total_rating_count", 0)) if pool else None
        return pick, results

    def time_to_beat(self, game_id: int):
        return self.query(
            "game_time_to_beats",
            f"fields game_id,hastily,normally,completely,count; where game_id = {game_id};",
        )

    def alt_names(self, game_id: int):
        """다나와 매칭용 이름 후보: 대체 이름(alternative_names) + 지역별 이름(game_localizations)."""
        alt = self.query(
            "alternative_names", f"fields name,comment; where game = {game_id}; limit 50;"
        )
        loc = self.query(
            "game_localizations", f"fields name,region.name; where game = {game_id}; limit 50;"
        )
        return {"alternative_names": alt, "localizations": loc}

    def external_games(self, game_id: int):
        for fields in ("uid,url,category,external_game_source", "uid,url,category", "uid,url"):
            try:
                return self.query(
                    "external_games", f"fields {fields}; where game = {game_id}; limit 50;"
                )
            except RuntimeError:
                continue
        return []


def steam_appid_from_external(rows: list[dict]) -> int | None:
    for row in rows:
        m = re.search(r"store\.steampowered\.com/app/(\d+)", row.get("url") or "")
        if m:
            return int(m.group(1))
    for row in rows:  # url 이 비어 있는 경우: Steam 소스 코드(1)
        if (row.get("category") == 1 or row.get("external_game_source") == 1) and str(
            row.get("uid", "")
        ).isdigit():
            return int(row["uid"])
    return None


def igdb_aliases(raw: dict, known: list[str]) -> list[str]:
    """IGDB 이름 데이터에서 다나와 상품명 매칭에 쓸 별칭을 고른다(오탐을 줄이려고 보수적으로).

    채택: 한국(Korea) 지역 이름, 'Korean …' 설명이 붙은 대체 이름, 영문 표기 변형(Alternative spelling/title,
          Stylized title, Acronym/Abbreviation 중 충분히 긴 것).
    제외: 실행 파일명(.exe), 한글·영문이 아닌 문자(중국어·러시아어 등), 에디션 이름, 이론상 제목,
          너무 짧은 영문(5자 미만, 숫자가 있으면 4자 미만) 약어. 이미 아는 이름과 같은 것도 뺀다.
    """
    cands: list[tuple[str, str]] = []
    for x in raw.get("localizations", []):
        if (x.get("region") or {}).get("name") == "Korea" and x.get("name"):
            cands.append((x["name"], "loc-ko"))
    for x in raw.get("alternative_names", []):
        if x.get("name"):
            cands.append((x["name"], x.get("comment") or ""))
    have = {norm(k) for k in known if k}
    out: list[str] = []
    for name, why in cands:
        n = norm(name)
        if not n or n in have or any(n == norm(o) for o in out):
            continue
        if re.search(
            r"\.exe|executable|theoretical|chronological|edition|working", name + " " + why, re.I
        ):
            continue
        if re.search(
            r"[^\x00-\x7f가-힣ㄱ-ㅎ·™:：\- ]", name
        ):  # 한글·영문 외 문자(한자·가나·키릴 등)
            continue
        if not re.search(r"[가-힣]", name):  # 영문 이름
            if not re.search(r"alternative|stylized|acronym|abbreviation|spelling", why, re.I):
                continue
            if len(n) < (4 if re.search(r"\d", n) else 5):
                continue
        out.append(name)
    return out


# ---------------------------------------------------------------- Steam
def steam_check(appid: int):
    det = http(
        "GET",
        "https://store.steampowered.com/api/appdetails",
        steam_gate,
        params={"appids": appid, "cc": "kr", "l": "koreana"},
    ).json()
    # store.steampowered.com/appreviews 는 이 환경에서 홈으로 302 되어, 리뷰 요약은
    # IStoreBrowseService/GetItems(include_reviews)로 가져온다. (키 불필요, 응답 원본 저장)
    inp = {
        "ids": [{"appid": appid}],
        "context": {"language": "koreana", "country_code": "KR"},
        "data_request": {"include_reviews": True},
    }
    r = http(
        "GET",
        "https://api.steampowered.com/IStoreBrowseService/GetItems/v1/",
        steam_gate,
        params={"input_json": json.dumps(inp)},
        allow_redirects=False,
    )
    try:
        rev = r.json()
    except ValueError:
        rev = {
            "_error": f"JSON 아님 (HTTP {r.status_code}, content-type={r.headers.get('content-type')})"
        }
    return det, rev


def steam_reviews_text(appid: int, key: str | None = None, per_page: int = 20) -> dict:
    """리뷰 본문 1페이지. store.steampowered.com/appreviews 는 폐기(DEPRECATED)돼 이 환경에서 홈으로 302 된다.
    후속 IUserReviewsService/GetAppReviews 는 파라미터를 input_json 에 담고, 키는 선택(앱 연동 키면 한도만 높음).
    languages 가 비면 영어가 기본이라 한국어(koreana)를 명시한다. 응답에 success 필드가 없어 HTTP 상태로 판단한다.
    """
    inp = {
        "appid": appid,
        "languages": ["koreana"],
        "filter": 1,
        "purchase_type": 1,
        "review_type": 0,
        "num_per_page": per_page,
    }
    params = {"input_json": json.dumps(inp)}
    if key:
        params["key"] = key
    r = http(
        "GET",
        "https://api.steampowered.com/IUserReviewsService/GetAppReviews/v1/",
        steam_gate,
        params=params,
        allow_redirects=False,
    )
    try:
        j = r.json()
    except ValueError:
        return {"_error": f"JSON 아님 (HTTP {r.status_code})"}
    if r.status_code != 200:
        return {"_error": f"HTTP {r.status_code}"}
    return j.get("response", j)


# ---------------------------------------------------------------- ITAD
def itad_check(key: str, appid: int | None, title: str):
    base = "https://api.isthereanydeal.com"
    params = {"key": key}
    if appid:
        params["appid"] = str(
            appid
        )  # 숫자만. "app/<id>" 형식은 lookup/id/shop 용이라 여기서는 항상 found:false
    else:
        params["title"] = title
    lookup = http("GET", f"{base}/games/lookup/v1", itad_gate, params=params)
    lookup.raise_for_status()
    lookup_j = lookup.json()
    game = lookup_j.get("game") if lookup_j.get("found") else None
    lookup_j["_match"] = "appid" if (game and appid) else "title" if game else None

    def info_appid(gid: str):
        r = http("GET", f"{base}/games/info/v2", itad_gate, params={"key": key, "id": gid})
        return r.json().get("appid") if r.status_code == 200 else None

    if not game and appid:
        # appid 조회가 빗나가는 게임이 있다(예: 바이오하자드 4 리메이크). 제목으로 바로 재조회하면 appid 없는
        # 다른 항목(원작·별칭 항목)에 붙을 수 있어, 검색 결과 중 Steam appid 가 같은 항목을 먼저 찾는다.
        sr = http(
            "GET",
            f"{base}/games/search/v1",
            itad_gate,
            params={"key": key, "title": title, "results": 20},
        )
        cands = [
            g for g in (sr.json() if sr.status_code == 200 else []) if g.get("type") == "game"
        ][:6]
        tried = []
        for g in cands:
            got = info_appid(g["id"])
            tried.append({"id": g["id"], "slug": g.get("slug"), "appid": got})
            if got == appid:
                game = g
                lookup_j = {
                    "found": True,
                    "game": g,
                    "_match": "search+appid",
                    "_search_tried": tried,
                }
                break
        if not game:  # 그래도 없으면 마지막 수단: 제목 조회 (appid 일치 여부를 표시한다)
            lookup = http(
                "GET", f"{base}/games/lookup/v1", itad_gate, params={"key": key, "title": title}
            )
            lookup.raise_for_status()
            lookup_j = lookup.json()
            game = lookup_j.get("game") if lookup_j.get("found") else None
            lookup_j["_match"] = "title" if game else None
            lookup_j["_search_tried"] = tried
            if game:
                lookup_j["_appid_verified"] = info_appid(game["id"]) == appid
    history = None
    if game:
        h = http(
            "GET",
            f"{base}/games/history/v2",
            itad_gate,
            params={"key": key, "id": game["id"], "country": "KR"},
        )
        h.raise_for_status()
        history = h.json()
    return lookup_j, history


# ---------------------------------------------------------------- 다나와
class Danawa:
    HOST = "https://search.danawa.com"

    def __init__(self):
        r = http("GET", f"{self.HOST}/robots.txt", danawa_gate, headers={"User-Agent": UA})
        self.robots_text = r.text
        self.rp = urllib.robotparser.RobotFileParser()
        self.rp.parse(r.text.splitlines())
        delay = self.rp.crawl_delay(UA) or self.rp.crawl_delay("*") or 0
        danawa_gate.min_interval = max(3.0, float(delay))  # 규칙 3초 이상 + robots 지연
        print(f"  [다나와] robots Crawl-delay={delay} → 요청 간격 {danawa_gate.min_interval:.0f}초")

    def search(self, query: str):
        url = f"{self.HOST}/dsearch.php"
        full = f"{url}?query={requests.utils.quote(query)}"
        if not self.rp.can_fetch(UA, full):
            return None, "robots.txt 에서 차단된 경로"
        r = http(
            "GET",
            url,
            danawa_gate,
            params={"query": query},
            headers={"User-Agent": UA, "Accept-Language": "ko-KR,ko;q=0.9"},
        )
        if r.status_code != 200:
            return None, f"HTTP {r.status_code}"
        return r.text, None


def _clean(s: str) -> str:
    """내장 JSON 문자열 정리: \\uXXXX 복원 → HTML 엔티티 해제 → 강조 태그(<b>) 제거."""
    s = re.sub(r"\\+u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), s)
    for _ in range(2):  # &amp;lt;b&amp;gt; 처럼 이중 이스케이프된 경우가 있다
        s = htmllib.unescape(s)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", s)).strip()


def classify_platform(*texts: str | None) -> str:
    """번들명·카테고리·제목 순으로 보며 처음 맞는 플랫폼을 돌려준다. 못 찾으면 '불명'."""
    for t in texts:
        if not t:
            continue
        for plat, pat in PLATFORM_RULES:
            if re.search(pat, t, re.I):
                return plat
    return "불명"


def parse_danawa(html: str) -> list[dict]:
    """다나와 검색 결과 → 상품 목록 (필터링 없이 전부).

    1순위: 페이지에 내장된 Next.js 데이터(productSeq 객체). pcode·최저가·판매처 수·번들명
           ("PS5, 패키지디스크" 등)·카테고리가 구조화돼 있다. 결과가 1~2건인 페이지도 동일.
           - 상품 그룹의 변형(PC 키/PS4/PS5/중고)은 wishListBundleVal 로 묶여 있고,
             그룹명과 카테고리는 대표 상품에만 있어 변형에게 상속한다.
    폴백:   JSON-LD ItemList(가격 없음).  별도: 쇼핑몰 광고 카드(aria-label "상품명 12,345원").
    """
    p = html.replace('\\"', '"')
    seq = list(re.finditer(r'"productSeq":"([A-Za-z0-9_]+)"', p))
    objs: dict[str, dict] = {}
    shops: dict[str, dict] = {}  # 묶이지 않은 개별 판매처 상품 (productSeq = 판매처코드_번호)
    for i, m in enumerate(seq):
        w = p[
            m.start() : min(seq[i + 1].start() if i + 1 < len(seq) else len(p), m.start() + 12000)
        ]
        if not m.group(1).isdigit():
            if m.group(1) in shops:
                continue
            cats4 = [int(x) for x in re.findall(r'"categorySeq[1-4]":(\d+)', w)[:4]]
            nm = re.search(r'"categoryNameList":\[([^\]]*)\]', w)
            pr = re.search(r'"minPrice":(\d+)', w)
            post = re.search(r'"postPrice":(\d+)', w)
            shops[m.group(1)] = {
                "listing_id": m.group(1),
                "title": _clean((re.search(r'"productName":"([^"]*)"', w) or [None, ""])[1]),
                "shop": (re.search(r'"shopName":"([^"]*)"', w) or [None, None])[1],
                "company_code": (re.search(r'"companyCode":"([^"]*)"', w) or [None, None])[1],
                "min_price": int(pr.group(1)) if pr else None,
                "post_price": int(post.group(1)) if post else None,
                "posted": (re.search(r'"printDate":"([^"]*)"', w) or [None, None])[1],
                "cate_ids": cats4,
                "category": [_clean(x) for x in re.findall(r'"([^"]*)"', nm.group(1))]
                if nm
                else None,
            }
            continue

        def num(key: str):
            mm = re.search(rf'"{key}":"?(\d+)', w)
            return int(mm.group(1)) if mm else None

        def txt(key: str):
            mm = re.search(rf'"{key}":"([^"]*)"', w)
            return _clean(mm.group(1)) if mm else None

        cats = re.search(r'"categoryNameList":\[([^\]]*)\]', w)
        o = {
            "pcode": m.group(1),
            "name": txt("productName"),
            "bundle": txt("bundleName"),
            "min_price": num("minPrice"),
            "shop_count": num("shopCount"),
            "release": txt("initialPrice"),
            "category": [_clean(x) for x in re.findall(r'"([^"]*)"', cats.group(1))]
            if cats
            else None,
        }
        prev = objs.setdefault(m.group(1), o)
        for k, v in o.items():  # 같은 pcode 가 여러 번 나오므로 빈 값만 채워 합친다
            if prev.get(k) in (None, "", []) and v not in (None, "", []):
                prev[k] = v

    groups: dict[str, dict] = {}
    for m in re.finditer(r'"wishListBundleVal":"([^"]*)"', p):
        parts = m.group(1).split("//")
        members = [v.split("^", 1) for v in parts[0].split("**") if "^" in v]
        cat = next(
            (objs[pc]["category"] for _, pc in members if pc in objs and objs[pc].get("category")),
            None,
        )
        gname = _clean(parts[1]) if len(parts) > 1 else None
        for label, pc in members:
            groups[pc] = {"group_name": gname, "label": _clean(label), "category": cat}

    items: list[dict] = []
    for pc, o in objs.items():
        g = groups.get(pc, {})
        cat = o.get("category") or g.get("category")
        bundle = o.get("bundle") or g.get("label")
        title = o.get("name") or g.get("group_name") or ""
        plat = classify_platform(bundle, " ".join(cat or []), title)
        rel = re.search(r"([\d,]+)\s*원", o.get("release") or "")
        items.append(
            {
                "source": "catalog",
                "pcode": pc,
                "title": title,
                "bundle": bundle,
                "platform": plat,
                "platform_kind": "console"
                if plat in CONSOLE_PLATFORMS
                else "pc"
                if plat == "PC"
                else "unknown",
                "is_game": bool(cat and cat[0] == "게임") if cat else None,
                "category": cat,
                "is_used": "중고" in (bundle or ""),
                "is_code": bool(re.search(r"코드|다운로드", bundle or "")),
                "min_price": o["min_price"] or None,  # 0 = 판매처 없음
                "shop_count": o["shop_count"],
                "release_price": int(rel.group(1).replace(",", "")) if rel else None,
            }
        )

    for sh in shops.values():
        cat = sh["category"]
        plat = classify_platform(sh["title"])
        if plat == "불명" and cat and any("PC" in c for c in cat):
            plat = "PC"
        c1 = sh["cate_ids"][0] if sh["cate_ids"] else None
        items.append(
            {
                "source": "shop_listing",
                "pcode": None,
                **sh,
                "bundle": None,
                "platform": plat,
                "platform_kind": "console"
                if plat in CONSOLE_PLATFORMS
                else "pc"
                if plat == "PC"
                else "unknown",
                "is_game": (c1 == 1393)
                if c1
                else None,  # 게임 대분류 코드. 0/없음은 판정 불가(None)
                "is_used": False,
                "is_code": bool(re.search(r"코드|다운로드|키", sh["title"])),
                "shop_count": 0,
                "release_price": None,
            }
        )

    if not items:  # 폴백: JSON-LD (가격 없음)
        for m in re.finditer(r'"@type":"ListItem","name":"([^"]+)","url":"[^"]*?pcode=(\d+)', html):
            t = _clean(m.group(1))
            plat = classify_platform(t)
            items.append(
                {
                    "source": "catalog",
                    "pcode": m.group(2),
                    "title": t,
                    "bundle": None,
                    "platform": plat,
                    "platform_kind": "console"
                    if plat in CONSOLE_PLATFORMS
                    else "pc"
                    if plat == "PC"
                    else "unknown",
                    "is_game": None,
                    "category": None,
                    "is_used": False,
                    "is_code": False,
                    "min_price": None,
                    "shop_count": None,
                    "release_price": None,
                }
            )

    for m in re.finditer(
        r'aria-label="([^"]*?)\s+([\d,]+)원"', html
    ):  # 광고 카드는 참고용으로만 보관
        t = _clean(m.group(1))
        items.append(
            {
                "source": "ad_card",
                "pcode": None,
                "title": t,
                "bundle": None,
                "platform": classify_platform(t),
                "platform_kind": "unknown",
                "is_game": None,
                "category": None,
                "is_used": False,
                "is_code": False,
                "min_price": int(m.group(2).replace(",", "")),
                "shop_count": None,
                "release_price": None,
            }
        )
    for it in items:
        if it["source"] in ("catalog", "shop_listing"):
            enrich_item(it)
    return items


EDITION_RULES = [  # (토큰명, 패턴) - 제목·번들명에서 찾는다. 하나라도 있으면 본편(is_base)이 아니다.
    ("DLC", r"확장팩|DLC|시즌\s*패스|추가\s*(컨텐츠|콘텐츠)|Separate\s*Ways|Add-?on|애드온"),
    ("골드", r"골드\s*에디션|골드판"),
    ("얼티밋", r"얼티밋|Ultimate"),
    ("GOTY", r"GOTY|고티|Game of the Year"),
    ("컴플리트", r"컴플리트|Complete"),
    ("디럭스", r"디럭스|Deluxe|디지털디럭스"),
    ("컬렉터즈", r"컬렉터|Collector"),
    ("프리미엄", r"프리미엄|Premium"),
    ("리마스터", r"리마스터|Remaster"),
    ("마스터에디션", r"마스터\s*에디션"),
    ("에디션(기타)", r"에디션|Edition"),
    ("번들(+구성품)", r"\+\s*\S*(피규어|굿즈|아트북|[0-9]종)"),
    ("DAY1/2", r"DAY\s*[12]"),
    ("CIB", r"CIB"),
    (
        "콘솔본체번들",
        r"CUH-|CFI-|플레이스테이션\s*[45]\s*(\(|\+)|엑스박스\s*(시리즈|원)?\s*[XS]?\s*\+|1TB|825GB",
    ),
    (
        "비게임",
        r"아트북|피규어|사운드트랙|OST|컨트롤러|파우치|케이스|마우스\s*패드|장패드|키보드|매트|"
        r"액세서리|악세서리|키링|열쇠고리|스티커|포스터|공략|가이드|Guide|Wiki|Books?\b|굿즈|거치대|스탠드|보호\s*필름|데스크탑|헤드셋|이어폰|충전|케이블|모니터|게이밍\s*(마우스|키보드)",
    ),
]
MEDIUM_RULES = [
    ("code", r"코드"),
    ("cartridge", r"패키지칩|패키지키카드|카트리지"),
    ("disc", r"패키지디스크|디스크"),
]
REGION_IMPORT = r"해외구매|해외직구|\[해외\]|일본판|유럽판|아시아판|북미판|수입"


def enrich_item(it: dict) -> None:
    """번들명·제목에서 매체/상태/언어·지역/에디션 토큰을 뽑는다 (원문은 그대로 두고 필드만 추가)."""
    bundle, title = it.get("bundle") or "", it.get("title") or ""
    text = f"{title} {bundle}"
    src = (
        bundle or title if it.get("source") == "shop_listing" else bundle
    )  # 개별 판매처 상품은 제목에서
    it["medium"] = next((m for m, pat in MEDIUM_RULES if re.search(pat, src)), None)
    it["condition"] = "used" if "중고" in src else "new"
    if it.get("source") == "shop_listing":
        it["is_used"] = it["condition"] == "used"
    it["region_lang"] = (
        "import" if re.search(REGION_IMPORT, text) else "ko" if "한글판" in text else None
    )
    toks = [name for name, pat in EDITION_RULES if re.search(pat, text, re.I)]
    if "마스터에디션" in toks or any(
        t in toks for t in ("골드", "컴플리트", "디럭스", "컬렉터즈", "프리미엄", "GOTY", "얼티밋")
    ):
        toks = [t for t in toks if t != "에디션(기타)"]
    it["edition_tokens"] = toks
    it["is_base"] = not toks


def name_variants(name: str) -> list[str]:
    """영문 제목 표기 차이를 흡수한다: 앞의 'The ' 제거, 숫자가 든 앞부분만 남기는 부제 제거.

    'The Witcher 3: Wild Hunt' -> 'Witcher 3: Wild Hunt', 'Witcher 3'.
    'Monster Hunter: World' 는 앞부분에 숫자가 없어 부제를 떼지 않는다('Monster Hunter' 는 너무 넓다).
    """
    out = [name]
    base = re.sub(r"^the\s+", "", name, flags=re.I)
    if base != name:
        out.append(base)
    head = re.split(r"\s*[:\-–]\s*", base, maxsplit=1)[0]
    if head != base and re.search(r"\d", head) and len(norm(head)) >= 5:
        out.append(head)
    return out


def parse_page_meta(html: str) -> dict:
    """검색 결과 응답에 들어 있는 전체 규모 정보. 한 페이지는 40건이라 1페이지만으로 전체를 다 봤는지 판단하는 근거가 된다.

    total_items: 검색 결과 전체 건수, total_pages/current_page: 페이지 정보,
    cat_*: 카테고리별 건수(게임 1393 / 콘솔게임 200028 / PC 1403 / 게임주변기기 58587).
    """
    p = html.replace('\\"', '"')
    m = re.search(r'"count":\{"total":(\d+)', p)
    pg = re.search(r'"page":\{"total":(\d+),"current":(\d+)\}', p)
    meta = {
        "total_items": int(m.group(1)) if m else None,
        "total_pages": int(pg.group(1)) if pg else None,
        "current_page": int(pg.group(2)) if pg else None,
    }
    cl = re.search(r'"category":\{"list":(\[.*?\])\},"', p)
    cats = {}
    if cl:
        for c1 in re.finditer(
            r'\{"cate":"(\d+)","cateName":"([^"]*)","groupCount":"(\d+)"', cl.group(1)
        ):
            cats[c1.group(1)] = int(c1.group(3))
        for c2 in re.finditer(
            r'\{"cate2":"(\d+)","cateName":"([^"]*)","groupCount":"(\d+)"', cl.group(1)
        ):
            cats[c2.group(1)] = int(c2.group(3))
    meta.update(
        cat_game=cats.get("1393"),
        cat_console=cats.get("200028"),
        cat_pc=cats.get("1403"),
        cat_accessory=cats.get("58587"),
    )
    return meta


def annotate_names(items: list[dict], names: list[str]) -> None:
    """각 항목에 name_match(후보 이름 중 하나가 제목에 포함되는지)를 기록한다."""
    keys = [norm(v) for n in names if n for v in name_variants(n)]
    for it in items:
        it["name_match"] = any(k in norm(it["title"]) for k in keys)


def select_hits(items: list[dict], kind: str, exclude: str | None = None) -> list[dict]:
    """kind('console'|'pc') 판정용 항목(에디션·DLC 포함). 카탈로그 + 게임 카테고리 + 이름 일치만.

    가격은 요구하지 않는다(판매처 0곳이면 price 가 None). 후보별 제외어는 뺀다. 본편/에디션 구분은 is_base.
    """
    out = []
    for it in items:
        if it["source"] != "catalog" or it["platform_kind"] != kind or not it["name_match"]:
            continue
        if it["is_game"] is False:  # 낚싯대·스탠드 등 비게임 상품
            continue
        text = f"{it['title']} {it['bundle'] or ''}"
        if exclude and re.search(exclude, text, re.I):
            continue
        out.append(it)
    return out


def select_listings(items: list[dict], exclude: str | None = None) -> list[dict]:
    """개별 판매처 상품 중 '이 후보의 게임'으로 보이는 것만 고른다 (가격 계산에는 아직 안 씀).

    1순위: 다나와 카테고리가 게임(c1=1393) → game_filter="category"
    2순위: 카테고리가 게임이 아니거나 미지정이어도 제목에 플랫폼이 있으면 → "title"
           (예: 카테고리가 도매/기타로 잘못 달린 'WHV GAMES [해외] ... Xbox')
    제외: 이름 불일치, 플랫폼 불명, 비게임 토큰(아트북·피규어·OST 등), 후보별 제외어.
    """
    out = []
    for it in items:
        if it["source"] != "shop_listing" or not it["name_match"]:
            continue
        if it["platform_kind"] == "unknown" or "비게임" in it["edition_tokens"]:
            continue
        if exclude and re.search(exclude, it["title"], re.I):
            continue
        it["game_filter"] = "category" if it["is_game"] else "title"
        out.append(it)
    return out


def cheapest(hits: list[dict], new_only: bool = False) -> dict | None:
    pool = [h for h in hits if h["min_price"] and not (new_only and h["is_used"])]
    return min(pool, key=lambda h: h["min_price"]) if pool else None


PRICE_PLATFORMS = ["PS5", "PS4", "Switch2", "Switch", "XboxSeries", "XboxOne", "Xbox", "PC"]


IGDB_PLATFORM_KEY = {
    "PlayStation 5": "PS5",
    "PlayStation 4": "PS4",
    "Nintendo Switch": "Switch",
    "Nintendo Switch 2": "Switch2",
    "Xbox Series X|S": "XboxSeries",
    "Xbox One": "XboxOne",
    "PC (Microsoft Windows)": "PC",
}
PLATFORM_QUERY_TERM = {
    "PS5": "PS5",
    "PS4": "PS4",
    "Switch": "스위치",
    "Switch2": "스위치2",
    "XboxSeries": "엑스박스 시리즈",
    "XboxOne": "엑스박스 원",
    "PC": "PC",
}


def missing_platforms(items: list[dict], want: set[str], exclude: str | None) -> list[str]:
    """IGDB 플랫폼 중 '개별 판매처 상품'이 한 건도 통과하지 못한 플랫폼. 세대 불명 Xbox 는 두 세대를 모두 채운 걸로 본다."""
    have = {h["platform"] for h in select_listings(items, exclude)}
    if "Xbox" in have:
        have |= {"XboxSeries", "XboxOne"}
    return [pl for pl in PRICE_PLATFORMS if pl in want and pl not in have]


def merge_items(base: list[dict], extra: list[dict], query: str) -> int:
    """추가 검색 결과를 중복 없이 합친다(카탈로그는 pcode, 개별 상품은 listing_id 기준). 새로 들어온 수를 반환."""
    seen = {
        (it["source"], it.get("pcode") or it.get("listing_id"))
        for it in base
        if it["source"] in ("catalog", "shop_listing")
    }
    n = 0
    for it in extra:
        if it["source"] == "ad_card":
            continue
        k = (it["source"], it.get("pcode") or it.get("listing_id"))
        if k in seen:
            continue
        seen.add(k)
        it["found_via"] = query
        base.append(it)
        n += 1
    return n


FLAG_LABEL = {
    "single_source": "가격 있는 상품 1건뿐",
    "few_shops": "판매처 2곳 미만",
    "new_vs_used": "신품/중고 가격 역전·3배 이상",
}


def flag_slots(pbp: dict) -> None:
    """최저가 칸마다 이상값 의심 표시(flags)를 붙인다. 값은 바꾸거나 빼지 않는다.

    single_source: 가격이 있는 상품이 1건뿐. few_shops: 최저가가 카탈로그 상품인데 판매처가 2곳 미만.
    new_vs_used:   같은 플랫폼에서 신품이 중고의 3배 이상이거나 중고가 신품보다 비쌈.
    """
    for conds in pbp.values():
        new = (conds.get("new") or {}).get("min")
        used = (conds.get("used") or {}).get("min")
        for cd, slot in conds.items():
            m = slot["min"]
            if not m:
                continue
            flags = []
            if slot["priced"] == 1:
                flags.append("single_source")
            if m["source"] == "catalog" and (m["shop_count"] or 0) < 2:
                flags.append("few_shops")
            if new and used and (used["price"] > new["price"] or new["price"] >= 3 * used["price"]):
                flags.append("new_vs_used")
            slot["flags"] = flags


def price_by_platform(hits: list[dict]) -> dict:
    """본편 항목을 플랫폼 x 상태(new/used)로 나눠 최저가 1건씩 고른다.

    가격이 없는(판매처 0곳) 상품은 최저가 후보에서 빠지지만 items 개수에는 센다.
    """
    out: dict = {}
    for h in hits:
        slot = out.setdefault(h["platform"], {}).setdefault(
            h["condition"], {"items": 0, "priced": 0, "min": None}
        )
        slot["items"] += 1
        if h["min_price"]:
            slot["priced"] += 1
            if slot["min"] is None or h["min_price"] < slot["min"]["price"]:
                slot["min"] = {
                    "price": h["min_price"],
                    "source": h["source"],
                    "pcode": h.get("pcode"),
                    "listing_id": h.get("listing_id"),
                    "shop": h.get("shop"),
                    "title": h["title"],
                    "bundle": h["bundle"],
                    "medium": h["medium"],
                    "region_lang": h["region_lang"],
                    "shop_count": h["shop_count"],
                    "post_price": h.get("post_price"),
                    "found_via": h.get("found_via"),
                    "edition_tokens": h.get("edition_tokens"),
                }
    return out


# ---------------------------------------------------------------- 메인
CSV_COLUMNS = [
    "후보",
    "igdb_id",
    "igdb_name",
    "igdb_platforms",
    "igdb_aliases",
    "ttb_있음",
    "ttb_채워진필드",
    "ttb_count",
    "steam_appid",
    "steam_pc_requirements",
    "steam_review_ko_total",
    "steam_review_ko_positive_pct",
    "steam_review_ko_label",
    "steam_review_all_total",
    "steam_review_all_positive_pct",
    "steam_reviews_text_total",
    "steam_reviews_text_positive_pct",
    "steam_reviews_text_fetched",
    "steam_reviews_text_nonempty",
    "steam_reviews_text_has_cursor",
    "steam_recommendations_all_lang",
    "itad_found",
    "itad_id",
    "itad_history_count",
    "danawa_catalog_items",
    "danawa_game_items",
    "danawa_console_found",
    "danawa_console_platforms",
    "danawa_console_min_krw",
    "danawa_console_min_new_krw",
    "danawa_console_cheapest",
    "danawa_pc_key_found",
    "danawa_pc_key_min_krw",
    "danawa_pc_key_cheapest",
    "danawa_total_items",
    "danawa_total_pages",
    "danawa_cat_game",
    "danawa_cat_console",
    "danawa_cat_pc",
    "danawa_cat_accessory",
    "danawa_pages_fetched",
    "danawa_game_seen_ratio",
    "danawa_platforms_without_listing",
    "danawa_price_sources",
    "danawa_price_flags",
    "danawa_edition_fallback",
    "danawa_shop_listing_items",
    "danawa_shop_game_items",
    "danawa_shop_matched_items",
    "danawa_shop_matched_by_title",
    "danawa_console_import_only",
    "danawa_pc_key_import_only",
    "danawa_import_items",
    "danawa_import_prices",
    "danawa_unmatched_game_items",
    "danawa_edition_items",
    "danawa_edition_tokens",
    *[f"danawa_{pl}_{cd}_krw" for pl in PRICE_PLATFORMS for cd in ("new", "used")],
    "notes",
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="이 문자열이 한글명에 포함된 후보만 실행")
    ap.add_argument("--skip-danawa", action="store_true")
    ap.add_argument(
        "--no-platform-queries",
        action="store_true",
        help="빈 플랫폼 보강 검색(예: '위쳐 3 스위치')을 하지 않는다",
    )
    ap.add_argument(
        "--reuse-danawa",
        action="store_true",
        help="samples 에 저장된 다나와 HTML 을 재사용(재요청 없음)",
    )
    args = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):  # Windows 콘솔(cp949)에서 한글 깨짐 방지
        sys.stdout.reconfigure(encoding="utf-8")

    load_dotenv(ROOT / ".env")
    missing = [k for k in REQUIRED_ENV if not os.getenv(k)]
    if missing:
        print(f".env 에 값이 없는 변수: {', '.join(missing)}")
        return 1
    _SECRETS.update(os.environ[k] for k in REQUIRED_ENV)

    cands = [c for c in CANDIDATES if not args.only or args.only in c["ko"]]
    igdb = Igdb(os.environ["IGDB_CLIENT_ID"], os.environ["IGDB_CLIENT_SECRET"])
    danawa = None
    if not args.skip_danawa:
        try:
            danawa = Danawa()
        except Exception as e:  # noqa: BLE001
            print(f"  [다나와] robots.txt 확인 실패 → 다나와 건너뜀: {redact(e)}")

    rows = []
    row_price_detail: dict = {}
    for i, c in enumerate(cands, 1):
        slug = f"{i:02d}_{re.sub(r'[^a-z0-9]+', '_', c['en'].lower()).strip('_')}"
        row = {k: "" for k in CSV_COLUMNS}
        row["후보"] = c["ko"]
        notes: list[str] = []
        print(f"[{i}/{len(cands)}] {c['ko']}")

        # 1) IGDB
        appid = None
        igdb_keys: set[str] = set()
        igdb_alias: list[str] = []
        try:
            pick, search_raw = igdb.find_game(c["en"], c.get("year"))
            save_json(OUT_DIR / "igdb" / f"{slug}_search.json", search_raw)
            if pick:
                gid = pick["id"]
                igdb_keys = {
                    IGDB_PLATFORM_KEY[p["name"]]
                    for p in pick.get("platforms", [])
                    if p.get("name") in IGDB_PLATFORM_KEY
                }
                row.update(
                    igdb_id=gid,
                    igdb_name=pick["name"],
                    igdb_platforms="; ".join(p["name"] for p in pick.get("platforms", [])),
                )
                names_raw = igdb.alt_names(gid)
                save_json(OUT_DIR / "igdb" / f"{slug}_names.json", names_raw)
                known = [c["ko"], c["en"], pick["name"], *c.get("aliases", []), *c.get("names", [])]
                igdb_alias = igdb_aliases(names_raw, known)
                row["igdb_aliases"] = "; ".join(igdb_alias)
                ttb = igdb.time_to_beat(gid)
                ext = igdb.external_games(gid)
                save_json(OUT_DIR / "igdb" / f"{slug}_time_to_beat.json", ttb)
                save_json(OUT_DIR / "igdb" / f"{slug}_external_games.json", ext)
                filled = [
                    f
                    for f in ("hastily", "normally", "completely")
                    if ttb and ttb[0].get(f) is not None
                ]
                row.update(
                    ttb_있음=bool(filled),
                    ttb_채워진필드="; ".join(filled),
                    ttb_count=ttb[0].get("count") if ttb else None,
                )
                appid = steam_appid_from_external(ext)
            else:
                notes.append("IGDB 매칭 실패")
        except Exception as e:  # noqa: BLE001
            notes.append(f"IGDB 오류: {redact(e)}")

        # 2) Steam
        if appid:
            row["steam_appid"] = appid
            try:
                det, rev = steam_check(appid)
                rtxt = steam_reviews_text(appid, os.environ.get("STEAM_API_KEY"))
                save_json(OUT_DIR / "steam" / f"{slug}_reviews_text.json", rtxt)
                save_json(OUT_DIR / "steam" / f"{slug}_appdetails.json", det)
                save_json(OUT_DIR / "steam" / f"{slug}_reviews_summary.json", rev)
                entry = det.get(str(appid), {})
                if entry.get("success"):
                    pc = entry["data"].get("pc_requirements")
                    has = isinstance(pc, dict) and any(pc.values())
                    row["steam_pc_requirements"] = (
                        "min+rec"
                        if has and pc.get("minimum") and pc.get("recommended")
                        else "min만"
                        if has and pc.get("minimum")
                        else "있음"
                        if has
                        else "없음"
                    )
                else:
                    notes.append("Steam appdetails success=false")
                if "_error" in rev:
                    notes.append(f"Steam 한국어 리뷰 수 조회 실패: {rev['_error']}")
                else:
                    items = rev.get("response", {}).get("store_items") or [{}]
                    rv = items[0].get("reviews") or {}
                    ko = rv.get("summary_language_specific") or {}
                    al = rv.get("summary_filtered") or {}
                    row["steam_review_ko_total"] = ko.get("review_count")
                    row["steam_review_ko_positive_pct"] = ko.get("percent_positive")
                    row["steam_review_ko_label"] = ko.get("review_score_label")
                    row["steam_review_all_total"] = al.get("review_count")
                    row["steam_review_all_positive_pct"] = al.get("percent_positive")
                    if not ko:
                        notes.append("Steam 리뷰 요약(ko) 없음")
                if "_error" in rtxt:
                    notes.append(f"Steam 리뷰 본문 조회 실패: {rtxt['_error']}")
                else:
                    qs = rtxt.get("query_summary", {})
                    texts = [v.get("review", "") for v in rtxt.get("reviews", [])]
                    tot = qs.get("total_reviews") or rtxt.get("total_matching")
                    row.update(
                        steam_reviews_text_total=tot,
                        steam_reviews_text_positive_pct=(
                            round(100 * qs["total_positive"] / tot)
                            if tot and qs.get("total_positive") is not None
                            else ""
                        ),
                        steam_reviews_text_fetched=len(texts),
                        steam_reviews_text_nonempty=sum(1 for t in texts if t.strip()),
                        steam_reviews_text_has_cursor=bool(rtxt.get("cursor")),
                    )
                if entry.get("success"):  # 참고용: 전체 언어 합산 추천 수
                    row["steam_recommendations_all_lang"] = (
                        entry["data"].get("recommendations", {}).get("total")
                    )
            except Exception as e:  # noqa: BLE001
                notes.append(f"Steam 오류: {redact(e)}")
        else:
            notes.append("Steam appid 없음(IGDB external_games 에 Steam 미등록)")

        # 3) ITAD
        try:
            lookup, hist = itad_check(os.environ["ITAD_API_KEY"], appid, c["en"])
            save_json(OUT_DIR / "itad" / f"{slug}_lookup.json", lookup)
            if hist is not None:
                save_json(OUT_DIR / "itad" / f"{slug}_history.json", hist)
            row["itad_found"] = bool(lookup.get("found"))
            if lookup.get("found"):
                row["itad_id"] = lookup["game"]["id"]
                row["itad_history_count"] = len(hist) if isinstance(hist, list) else 0
                if lookup.get("_match") == "search+appid":
                    notes.append(
                        "ITAD: appid 조회 실패 → 검색 결과에서 Steam appid 가 같은 항목으로 매칭"
                    )
                if lookup.get("_appid_verified") is False:
                    notes.append(
                        "ITAD: 제목으로만 매칭됨, Steam appid 불일치 → 다른 게임 항목일 수 있음"
                    )
        except Exception as e:  # noqa: BLE001
            notes.append(f"ITAD 오류: {redact(e)}")

        # 4) 다나와
        if danawa:
            try:
                query = c["ko"]
                saved = OUT_DIR / "danawa" / f"{slug}_search.html"
                if (
                    args.reuse_danawa and saved.exists()
                ):  # 파서 수정 후 재검증용: 재요청 없이 저장본 사용
                    html, err = saved.read_text(encoding="utf-8"), None
                else:
                    html, err = danawa.search(query)
                if err:
                    notes.append(f"다나와: {err}")
                else:
                    (OUT_DIR / "danawa").mkdir(parents=True, exist_ok=True)
                    (OUT_DIR / "danawa" / f"{slug}_search.html").write_text(html, encoding="utf-8")
                    items = parse_danawa(html)
                    page_meta = parse_page_meta(html)
                    seen_game = sum(
                        1
                        for it in items
                        if it["source"] in ("catalog", "shop_listing") and it["is_game"]
                    )
                    page_meta["game_items_seen_page1"] = seen_game
                    cat_game = page_meta.get("cat_game")
                    row.update(
                        danawa_total_items=page_meta["total_items"],
                        danawa_total_pages=page_meta["total_pages"],
                        danawa_cat_game=cat_game,
                        danawa_cat_console=page_meta["cat_console"],
                        danawa_cat_pc=page_meta["cat_pc"],
                        danawa_cat_accessory=page_meta["cat_accessory"],
                        danawa_pages_fetched=1,
                        danawa_game_seen_ratio=round(seen_game / cat_game, 2) if cat_game else "",
                    )
                    for it in items:
                        it["found_via"] = query
                    names = (
                        c["names"] if "names" in c else [c["ko"], c["en"], *c.get("aliases", [])]
                    )
                    names = [*names, *[a for a in igdb_alias if a not in names]]
                    annotate_names(items, names)
                    exclude = c.get("danawa_exclude")

                    # 빈 플랫폼 보강: 기본 검색 1페이지(40건)에 안 들어온 플랫폼만 '<이름> <플랫폼>'으로 추가 검색
                    extra_queries: list[str] = []
                    if not args.no_platform_queries:
                        for pl in missing_platforms(items, igdb_keys, exclude):
                            q = f"{c['ko']} {PLATFORM_QUERY_TERM[pl]}"
                            f = OUT_DIR / "danawa" / f"{slug}_search_{pl}.html"
                            if (
                                args.reuse_danawa and f.exists()
                            ):  # 저장본이 있으면 재사용, 없으면 새로 요청
                                h2, e2 = f.read_text(encoding="utf-8"), None
                            else:
                                h2, e2 = danawa.search(q)
                            if e2:
                                notes.append(f"다나와 보강검색 '{q}' 실패: {e2}")
                                continue
                            f.write_text(h2, encoding="utf-8")
                            extra = parse_danawa(h2)
                            annotate_names(extra, names)
                            added = merge_items(items, extra, q)
                            extra_queries.append(f"{q}(+{added})")
                    if extra_queries:
                        notes.append("다나와 보강검색: " + ", ".join(extra_queries))
                    left = missing_platforms(items, igdb_keys, exclude)
                    row["danawa_platforms_without_listing"] = "; ".join(left)

                    con_all = select_hits(items, "console", exclude)
                    pck_all = select_hits(items, "pc", exclude)
                    lst_title = select_listings(items, exclude)  # 카테고리+제목 폴백 전체
                    lst_all = [
                        h for h in lst_title if h["game_filter"] == "category"
                    ]  # 가격 계산용
                    con_all = [h for h in con_all if h["source"] == "catalog"]
                    base_con = [
                        h
                        for h in con_all + lst_all
                        if h["is_base"] and h["platform_kind"] == "console"
                    ]
                    base_pck = [
                        h for h in pck_all + lst_all if h["is_base"] and h["platform_kind"] == "pc"
                    ]
                    is_imp = lambda h: h["region_lang"] == "import"  # noqa: E731
                    # 해외판/수입은 별도 표시: 국내 가격 열·최저가에서 빼고 import 전용 열에 따로 둔다.
                    con = [h for h in base_con if not is_imp(h)]
                    pck = [h for h in base_pck if not is_imp(h)]
                    imp = [h for h in base_con + base_pck if is_imp(h)]
                    editions = [h for h in con_all + pck_all + lst_all if not h["is_base"]]
                    catalog = [it for it in items if it["source"] == "catalog"]
                    games = [it for it in catalog if it["is_game"] is not False]
                    unmatched = [
                        it
                        for it in games
                        if not it["name_match"] and it["platform_kind"] != "unknown"
                    ]
                    listings = [it for it in items if it["source"] == "shop_listing"]
                    matched = select_listings(items, exclude)
                    pbp, pbp_imp = price_by_platform(con + pck), price_by_platform(imp)
                    # 에디션은 별도 보관. 본편 가격이 없는 (플랫폼, 상태) 칸에만 '대체 표시'로 쓴다(국내판만).
                    flag_slots(pbp)
                    flag_slots(pbp_imp)
                    pbp_ed = price_by_platform([h for h in editions if not is_imp(h)])
                    pbp_ed_imp = price_by_platform([h for h in editions if is_imp(h)])
                    # DLC·확장팩은 본편 대용이 될 수 없으므로 대체 후보에서 뺀다(pbp_ed 에는 그대로 남는다).
                    pbp_fb = price_by_platform(
                        [h for h in editions if not is_imp(h) and "DLC" not in h["edition_tokens"]]
                    )
                    fallback = {}
                    for pl, conds in pbp_fb.items():
                        for cd, slot in conds.items():
                            if slot["min"] and not (pbp.get(pl, {}).get(cd) or {}).get("min"):
                                fallback.setdefault(pl, {})[cd] = slot["min"]
                    save_json(
                        OUT_DIR / "danawa" / f"{slug}_parsed.json",
                        {
                            "query": query,
                            "match_names": names,
                            "page_meta": page_meta,
                            "items": items,
                            "console_hits": [h["pcode"] for h in con],
                            "pc_key_hits": [h["pcode"] for h in pck],
                            "import_hits": [h["pcode"] for h in imp],
                            "edition_hits": [h["pcode"] for h in editions],
                            "shop_listing_hits": [h["listing_id"] for h in matched],
                            "price_by_platform": pbp,
                            "price_by_platform_import": pbp_imp,
                            "price_by_platform_edition": pbp_ed,
                            "price_by_platform_edition_import": pbp_ed_imp,
                            "edition_fallback": fallback,
                        },
                    )
                    fmt = lambda h: (
                        f"{h['title']} ({h.get('bundle') or h.get('shop')}) "  # noqa: E731
                        f"{h['min_price']:,}원"
                        if h
                        else ""
                    )
                    # found 는 '수집 가능 여부'라 해외판도 포함, 국내 가격이 없고 해외판만 있으면 import_only
                    row.update(
                        danawa_catalog_items=len(catalog),
                        danawa_game_items=len(games),
                        danawa_console_found=bool(base_con),
                        danawa_pc_key_found=bool(base_pck),
                        danawa_console_import_only=bool(base_con) and not con,
                        danawa_pc_key_import_only=bool(base_pck) and not pck,
                        danawa_unmatched_game_items=len(unmatched),
                        danawa_shop_listing_items=len(listings),
                        danawa_shop_game_items=sum(1 for it in listings if it["is_game"]),
                        danawa_shop_matched_items=len(matched),
                        danawa_shop_matched_by_title=sum(
                            1 for it in matched if it["game_filter"] == "title"
                        ),
                        danawa_edition_items=len(editions),
                        danawa_edition_tokens="; ".join(
                            sorted({t for h in editions for t in h["edition_tokens"]})
                        ),
                    )
                    if con:
                        row["danawa_console_platforms"] = "; ".join(
                            sorted({h["platform"] for h in con})
                        )
                        row["danawa_console_min_krw"] = (cheapest(con) or {}).get("min_price", "")
                        row["danawa_console_min_new_krw"] = (cheapest(con, True) or {}).get(
                            "min_price", ""
                        )
                        row["danawa_console_cheapest"] = fmt(cheapest(con))
                    if pck:
                        row["danawa_pc_key_min_krw"] = (cheapest(pck) or {}).get("min_price", "")
                        row["danawa_pc_key_cheapest"] = fmt(cheapest(pck))
                    for pl, conds in pbp.items():
                        for cd, slot in conds.items():
                            if slot["min"]:
                                row[f"danawa_{pl}_{cd}_krw"] = slot["min"]["price"]
                    row["danawa_import_items"] = len(imp)
                    row["danawa_import_prices"] = "; ".join(
                        f"{pl} {'신품' if cd == 'new' else '중고'} {slot['min']['price']:,}원"
                        f"({slot['min']['bundle'] or slot['min']['shop']})"
                        for pl, conds in pbp_imp.items()
                        for cd, slot in conds.items()
                        if slot["min"]
                    )
                    row["danawa_price_sources"] = "; ".join(
                        f"{pl}/{cd}={slot['min']['source']}"
                        + (f":{slot['min']['shop']}" if slot["min"]["shop"] else "")
                        for pl, conds in pbp.items()
                        for cd, slot in conds.items()
                        if slot["min"]
                    )
                    row["danawa_price_flags"] = "; ".join(
                        f"{pl}/{cd}:{','.join(slot['flags'])}"
                        for pl, conds in pbp.items()
                        for cd, slot in conds.items()
                        if slot.get("flags")
                    )
                    row["danawa_edition_fallback"] = "; ".join(
                        f"{pl} {'신품' if cd == 'new' else '중고'} {m['price']:,}원"
                        f"[{'/'.join(m['edition_tokens'] or [])}]({m['source']}:{m['shop'] or m['bundle']})"
                        for pl, conds in fallback.items()
                        for cd, m in conds.items()
                    )
                    row_price_detail[c["ko"]] = {
                        "domestic": pbp,
                        "import": pbp_imp,
                        "edition": pbp_ed,
                        "edition_import": pbp_ed_imp,
                        "edition_fallback": fallback,
                    }
                    if imp:
                        notes.append(
                            f"다나와: 해외판/수입 본편 {len(imp)}건은 별도 열(danawa_import_*)로 분리"
                        )
                    if con_all and not base_con:
                        notes.append("다나와: 콘솔은 에디션 상품만 있음(본편 없음)")
                    if not catalog:
                        notes.append("다나와: 카탈로그 상품 0건(결과 없음/차단/구조 변경 가능)")
                    if unmatched:
                        notes.append(
                            f"다나와: 이름 불일치 게임 상품 {len(unmatched)}건(별칭 확인 필요)"
                        )
            except Exception as e:  # noqa: BLE001
                notes.append(f"다나와 오류: {redact(e)}")

        row["notes"] = " | ".join(notes)
        rows.append(row)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT_DIR / "result.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        w.writeheader()
        w.writerows(rows)
    save_json(
        OUT_DIR / "result.json",
        {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "rows": rows,
            "danawa_price_by_platform": row_price_detail,
        },
    )
    print(f"\n저장 완료: {OUT_DIR / 'result.csv'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
