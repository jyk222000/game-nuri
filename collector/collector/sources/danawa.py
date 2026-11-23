"""다나와 검색 결과 크롤링 → raw.console

게임마다 검색어(한글 이름, 없으면 영문 이름)로 `search.danawa.com/dsearch.php`의
**1페이지**만 받는다. 검색 결과 HTML에 내장된 Next.js 데이터에서 카탈로그 상품(pcode가 숫자)을
읽어 상품 1건 = 봉투 1개로 보낸다 (계약 `docs/contracts/messages/raw.console.json`).
게임과 상품의 연결(이름 매칭)은 정제기의 일이다.

지키는 규칙 (docs/collector-test/danawa-notes.md 9·11절)
- robots.txt를 시작할 때 읽어 금지 경로는 요청하지 않고, `Crawl-delay`(10초) 이상 간격을 둔다.
- `/api/`, `/bridge/` 등 금지 경로와 판매처 이동 링크는 호출하지 않는다 (검색 페이지만 받는다).
- User-Agent에 프로젝트명을 넣는다.
- 페이지 구조가 바뀌어 상품이 0건이면 경고를 남기고 멈추지 않는다.

이번 범위에서 뺀 것: 빈 플랫폼 보강 검색, 개별 판매처 상품(`shop_listing`), 2페이지 이후,
상세 페이지.
"""

from __future__ import annotations

import csv
import html as htmllib
import re
import time
import urllib.robotparser
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
from gamenuri_common.logging import get_logger
from gamenuri_common.messages import RawEnvelope

log = get_logger("collector.danawa")

HOST = "https://search.danawa.com"
SEARCH_URL = f"{HOST}/dsearch.php"
USER_AGENT = "game-nuri-collector/0.1 (student project; data pipeline course)"
MIN_INTERVAL_SEC = 10.0  # robots.txt Crawl-delay. 실행 때 robots 값이 더 크면 그 값을 쓴다
MAX_RETRIES = 3
BACKOFF_SEC = 30.0
DEFAULT_GAMES_FILE = (
    Path(__file__).resolve().parents[3] / "analysis" / "game_list" / "games_1000.csv"
)

CONSOLE_KEYS = {"PS5", "PS4", "Switch", "Switch2", "XboxSeries", "XboxOne"}
# 정제기(rules/console.py)가 받는 platform_hint. Xbox(세대 불명)는 hint 없이 상품명으로 판단한다.
SERVICE_PLATFORMS = {"PC", "PS4", "PS5", "Switch", "Switch2", "XboxOne", "XboxSeries"}

# 플랫폼 판별 (앞에서부터 먼저 맞는 것). 입력은 번들명 → 카테고리 → 제목 순.
PLATFORM_RULES = [
    ("Switch2", r"switch\s?2|스위치\s?2"),
    ("Switch", r"switch|스위치|닌텐도"),
    ("PS5", r"ps\s?5|플레이스테이션\s?5|플스\s?5"),
    ("PS4", r"ps\s?4|플레이스테이션\s?4|플스\s?4"),
    ("XboxSeries", r"(xbox|엑스박스)\s*(series|시리즈)|series\s*[xs]"),
    ("XboxOne", r"(xbox|엑스박스)\s*(one|원)|xbox\s*360"),
    ("Xbox", r"xbox|엑스박스"),
    ("PC", r"(?<![a-z])pc(?![a-z])|pc게임|스팀|steam|gog|에픽|epic"),
]
MEDIUM_RULES = [
    ("code", r"코드"),
    ("cartridge", r"패키지칩|패키지키카드|카트리지"),
    ("disc", r"패키지디스크|디스크"),
]
EDITION_OF_MEDIUM = {"code": "code", "disc": "physical", "cartridge": "physical"}


class DanawaError(RuntimeError):
    pass


@dataclass(frozen=True)
class Query:
    igdb_id: int
    text: str


def load_queries(path: Path = DEFAULT_GAMES_FILE, limit: int | None = None) -> list[Query]:
    """콘솔 플랫폼이 있는 게임만, rank 순으로. 검색어 = 한글 이름 → 없으면 영문 이름."""
    out: list[Query] = []
    seen: set[int] = set()
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            if not CONSOLE_KEYS & set((row.get("platforms") or "").split("|")):
                continue
            text = (row.get("name_ko") or row.get("name") or "").strip()
            gid = int(row["game_id"])
            if text and gid not in seen:
                seen.add(gid)
                out.append(Query(gid, text))
    return out[:limit] if limit else out


# ---------------------------------------------------------------- 파싱
def _clean(s: str) -> str:
    """내장 JSON 문자열 정리: \\uXXXX 복원 → HTML 엔티티 해제 → 강조 태그(<b>) 제거."""
    s = re.sub(r"\\+u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), s)
    for _ in range(2):  # &amp;lt;b&amp;gt; 처럼 이중 이스케이프된 경우가 있다
        s = htmllib.unescape(s)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", s)).strip()


def classify_platform(*texts: str | None) -> str | None:
    for t in texts:
        if not t:
            continue
        for plat, pat in PLATFORM_RULES:
            if re.search(pat, t, re.I):
                return plat
    return None


def parse_catalog(html: str) -> list[dict[str, Any]]:
    """검색 결과 → 카탈로그 상품 목록 (pcode가 숫자인 것). 필터링 없이 전부.

    같은 상품 그룹의 변형(PS4/PS5/중고 등)은 `wishListBundleVal`로 묶여 있고, 그룹 이름과
    카테고리는 대표 상품에만 있어 변형에게 이어 준다.
    """
    p = html.replace('\\"', '"')
    seq = list(re.finditer(r'"productSeq":"(\d+)"', p))
    allseq = list(re.finditer(r'"productSeq":"([A-Za-z0-9_]+)"', p))
    ends = {
        m.start(): (allseq[i + 1].start() if i + 1 < len(allseq) else len(p))
        for i, m in enumerate(allseq)
    }
    objs: dict[str, dict[str, Any]] = {}
    for m in seq:
        w = p[m.start() : min(ends[m.start()], m.start() + 12000)]

        def num(key: str, w: str = w) -> int | None:
            mm = re.search(rf'"{key}":"?(\d+)', w)
            return int(mm.group(1)) if mm else None

        def txt(key: str, w: str = w) -> str | None:
            mm = re.search(rf'"{key}":"([^"]*)"', w)
            return _clean(mm.group(1)) if mm else None

        cats = re.search(r'"categoryNameList":\[([^\]]*)\]', w)
        o = {
            "pcode": m.group(1),
            "name": txt("productName"),
            "bundle": txt("bundleName"),
            "min_price": num("minPrice"),
            "shop_count": num("shopCount"),
            "release_price_text": txt("initialPrice"),
            "category": [_clean(x) for x in re.findall(r'"([^"]*)"', cats.group(1))]
            if cats
            else None,
        }
        prev = objs.setdefault(m.group(1), o)
        for k, v in o.items():  # 같은 pcode가 여러 번 나오므로 빈 값만 채워 합친다
            if prev.get(k) in (None, "", []) and v not in (None, "", []):
                prev[k] = v

    groups: dict[str, dict[str, Any]] = {}
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

    items: list[dict[str, Any]] = []
    for pc, o in objs.items():
        g = groups.get(pc, {})
        items.append(
            {
                "pcode": pc,
                "title": o.get("name") or g.get("group_name") or "",
                "bundle": o.get("bundle") or g.get("label"),
                "category": o.get("category") or g.get("category"),
                "min_price": o["min_price"] or None,  # 0 = 판매처 없음
                "shop_count": o["shop_count"],
                "release_price_text": o["release_price_text"],
            }
        )
    return items


def to_payload(it: dict[str, Any]) -> dict[str, Any]:
    """카탈로그 상품 → raw.console payload (계약 필드 + condition·medium + 원문 보조 필드)."""
    bundle, title = it.get("bundle") or "", it["title"]
    plat = classify_platform(bundle, " ".join(it.get("category") or []), title)
    medium = next((m for m, pat in MEDIUM_RULES if re.search(pat, bundle)), None)
    return {
        "pcode": it["pcode"],
        "product_name": title,
        "platform_hint": plat if plat in SERVICE_PLATFORMS else None,
        "edition": EDITION_OF_MEDIUM.get(medium, "physical"),
        "medium": medium,
        "condition": "used" if "중고" in bundle else "new",
        "lowest_price": it["min_price"],
        "shop_count": it["shop_count"],
        "url": f"https://prod.danawa.com/info/?pcode={it['pcode']}",
        "bundle_name": it.get("bundle"),
        "category": it.get("category"),
        "release_price_text": it.get("release_price_text"),
    }


def _is_game_category(it: dict[str, Any]) -> bool:
    cat = it.get("category")
    return bool(cat) and cat[0] == "게임"


# ---------------------------------------------------------------- 요청
class DanawaClient:
    """검색 페이지를 받는다. robots.txt와 호출 간격을 여기서 강제한다."""

    def __init__(
        self,
        session: requests.Session | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._s = session or requests.Session()
        self._sleep = sleep
        self._clock = clock
        self._last = float("-inf")
        self.interval = MIN_INTERVAL_SEC
        self._rp = urllib.robotparser.RobotFileParser()
        self._load_robots()

    def _load_robots(self) -> None:
        r = self._s.get(f"{HOST}/robots.txt", headers={"User-Agent": USER_AGENT}, timeout=30)
        if not r.ok:  # robots를 못 읽으면 안전하게 중단한다
            raise DanawaError(f"robots.txt를 읽지 못했다: HTTP {r.status_code}")
        self._rp.parse(r.text.splitlines())
        delay = self._rp.crawl_delay(USER_AGENT) or self._rp.crawl_delay("*") or 0
        self.interval = max(MIN_INTERVAL_SEC, float(delay))
        log.info("robots.txt Crawl-delay=%s → 요청 간격 %.0f초", delay, self.interval)

    def _throttle(self) -> None:
        wait = self.interval - (self._clock() - self._last)
        if wait > 0:
            self._sleep(wait)
        self._last = self._clock()

    def search(self, query: str) -> str:
        """검색 1페이지의 HTML. 오류 문구에는 검색어를 넣지 않는다."""
        url = f"{SEARCH_URL}?query={requests.utils.quote(query)}"
        if not self._rp.can_fetch(USER_AGENT, url):
            raise DanawaError("robots.txt가 막은 경로")
        for attempt in range(MAX_RETRIES + 1):
            self._throttle()
            r = self._s.get(
                SEARCH_URL,
                params={"query": query},
                headers={"User-Agent": USER_AGENT, "Accept-Language": "ko-KR,ko;q=0.9"},
                timeout=30,
            )
            if r.status_code == 429 or r.status_code >= 500:
                if attempt == MAX_RETRIES:
                    break
                delay = float(r.headers.get("Retry-After", BACKOFF_SEC * 2**attempt))
                log.warning(
                    "다나와 HTTP %s, %ss 후 재시도 (%s/%s)",
                    r.status_code,
                    delay,
                    attempt + 1,
                    MAX_RETRIES,
                )
                self._sleep(delay)
                continue
            if not r.ok:
                raise DanawaError(f"다나와 검색 HTTP {r.status_code}")
            return r.text
        raise DanawaError("다나와 검색 재시도 초과")


# ---------------------------------------------------------------- 수집
def collect(
    queries: list[Query], client: DanawaClient | None = None
) -> Iterator[tuple[str, RawEnvelope]]:
    """검색어마다 1페이지를 받아 (Kafka 키 = pcode, 봉투)를 낸다. 한 건 실패해도 계속한다.

    보내는 것: 게임 카테고리의 카탈로그 상품 중 가격(최저가)이 있는 것. 나머지(주변기기·책,
    판매처 없는 상품)는 정제기가 어차피 쓰지 않아 노이즈만 되므로 보내지 않고 개수를 로그로 남긴다.
    같은 pcode는 한 번의 실행에서 한 번만 보낸다.
    """
    client = client or DanawaClient()
    sent_pcodes: set[str] = set()
    stats = {"queries": 0, "failed": 0, "empty": 0, "sent": 0, "non_game": 0, "no_price": 0}
    for q in queries:
        stats["queries"] += 1
        try:
            html = client.search(q.text)
        except (DanawaError, requests.RequestException) as e:
            stats["failed"] += 1
            log.warning("다나와 igdb_id=%s 검색 실패: %s", q.igdb_id, type(e).__name__)
            continue
        items = parse_catalog(html)
        if not items:
            stats["empty"] += 1
            log.warning(
                "다나와 igdb_id=%s: 카탈로그 상품 0건 (결과 없음 또는 페이지 구조 변경)", q.igdb_id
            )
            continue
        for it in items:
            if not _is_game_category(it):
                stats["non_game"] += 1
            elif not it["min_price"]:
                stats["no_price"] += 1
            elif it["pcode"] not in sent_pcodes:
                sent_pcodes.add(it["pcode"])
                stats["sent"] += 1
                yield (
                    it["pcode"],
                    RawEnvelope(
                        source="danawa",
                        kind="console_price",
                        request={
                            "url": SEARCH_URL,
                            "params": {"query": q.text, "igdb_id": q.igdb_id},
                        },
                        payload=to_payload(it),
                    ),
                )
    log.info("다나와 수집 완료: %s", stats)
    if stats["queries"] >= 10 and stats["empty"] > stats["queries"] / 2:
        log.error("검색의 절반 이상이 0건이다. 페이지 구조가 바뀌었거나 차단됐을 수 있다")
