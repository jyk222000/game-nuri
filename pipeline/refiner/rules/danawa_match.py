"""다나와 상품 거르기와 상품명 → 게임 매칭 (순수 함수).

규칙 출처: docs/collector-test/danawa-notes.md 3·5·6·7·12·15절,
collector/experiments/check_candidates.py.

1) 거르기 (가격에는 국내판 본편만 쓴다, 6·7절)
   - 비게임(아트북·피규어·컨트롤러 등), 본체 번들(CUH-, 1TB 등), DLC·확장팩, 에디션(얼티밋·GOTY 등),
     해외판(해외구매·[해외]·일본판 등)은 refined.unmatched 로 이유를 남긴다.
2) 이름 매칭 (5·15절)
   - 상품명과 별칭을 정규화(소문자, 영숫자·한글만, 로마 숫자 → 아라비아)한 뒤
     별칭이 상품명 안에 들어 있으면 후보. 가장 긴 별칭의 게임에 배정한다
     (시리즈 후속작이 목록에 있으면 더 긴 이름이 이긴다: 하데스 < 하데스 2).
   - 별칭 바로 뒤에 붙은 숫자나 따로 떨어진 1~2자리 숫자가 오면 후속작으로 보고 일치로 보지 않는다
     (하데스 → 하데스2·하데스 2). 떨어진 3자리 이상 숫자(상품 코드, 연도)는 괜찮다.
   - 영문만으로 된 별칭은 5글자 이상만, 앞뒤가 영문자로 이어지면 일치로 보지 않는다
     (RE4·GOW 같은 약어, control → controller 방지).
   - 길이가 같은 별칭이 서로 다른 게임이면 배정하지 않는다 (확인 필요).
"""

from __future__ import annotations

import re
from typing import Any

# (이유, 패턴) — 위에서부터 먼저 맞는 것을 이유로 쓴다
EXCLUDE_RULES: list[tuple[str, str]] = [
    (
        "비게임 상품",
        r"아트북|피규어|사운드트랙|OST|컨트롤러|controller|파우치|케이스|마우스\s*패드|장패드|키보드|"
        r"매트|액세서리|악세서리|키링|열쇠고리|스티커|포스터|공략|가이드|Guide|Wiki|Books?\b|굿즈|"
        r"거치대|스탠드|보호\s*필름|데스크탑|헤드셋|이어폰|충전|케이블|모니터|게이밍\s*(마우스|키보드)",
    ),
    (
        "본체 번들",
        r"CUH-|CFI-|플레이스테이션\s*[45]\s*(\(|\+)|엑스박스\s*(시리즈|원)?\s*[XS]?\s*\+|1TB|825GB|"
        r"본체|콘솔\s*번들",
    ),
    (
        "해외판",
        r"해외구매|해외직구|\[해외\]|일본판|유럽판|아시아판|북미판|수입|일본발매|EU 버전|\[호환\]",
    ),
    ("DLC·확장팩", r"확장팩|DLC|시즌\s*패스|추가\s*(컨텐츠|콘텐츠)|Separate\s*Ways|Add-?on|애드온"),
    (
        "에디션 (본편 아님)",
        r"골드\s*에디션|골드판|얼티밋|Ultimate|GOTY|고티|Game of the Year|컴플리트|Complete|"
        r"디럭스|Deluxe|컬렉터|Collector|프리미엄|Premium|리마스터|Remaster|마스터\s*에디션|"
        r"에디션|Edition|\+\s*\S*(피규어|굿즈|아트북|[0-9]종)|DAY\s*[12]|CIB",
    ),
]
_EXCLUDE = [(reason, re.compile(p, re.I)) for reason, p in EXCLUDE_RULES]

ROMAN = {"ii": "2", "iii": "3", "iv": "4", "v": "5", "vi": "6", "vii": "7", "viii": "8"}
HANGUL = re.compile(r"[가-힣]")


def exclude_reason(title: str) -> str | None:
    """가격에 쓰지 않을 상품이면 이유, 아니면 None."""
    for reason, pat in _EXCLUDE:
        if pat.search(title):
            return reason
    return None


def norm(s: str) -> str:
    """소문자, 로마 숫자 단어 → 아라비아, 영숫자·한글만 남긴다."""
    words = re.split(r"[^0-9a-z가-힣]+", s.lower())
    return "".join(ROMAN.get(w, w) for w in words if w)


def norm_with_ends(s: str) -> tuple[str, set[int]]:
    """norm() 과 같은 문자열 + 원래 단어가 끝나던 위치 (공백·기호가 있던 자리)."""
    out = ""
    ends: set[int] = {0}
    for w in re.split(r"[^0-9a-z가-힣]+", s.lower()):
        if w:
            out += ROMAN.get(w, w)
            ends.add(len(out))
    return out, ends


def usable(key: str) -> bool:
    """매칭에 쓸 수 있는 별칭인지. 한글이 있으면 2글자 이상, 영문·숫자만이면 5글자 이상."""
    if HANGUL.search(key):
        return len(key) >= 2
    return len(key) >= 5


class TitleMatcher:
    """별칭 {원래 별칭: game_id} → 상품명 매칭. 별칭이 늘면 다시 만든다."""

    def __init__(self, aliases: dict[str, int]):
        self.size = len(aliases)
        index: dict[str, set[int]] = {}
        for alias, gid in aliases.items():
            k = norm(alias)
            if usable(k):
                index.setdefault(k, set()).add(int(gid))
        # 긴 별칭부터 본다
        self.keys = sorted(index, key=len, reverse=True)
        self.index = index

    def match(self, title: str) -> tuple[int | None, str]:
        """→ (game_id 또는 None, 이유)."""
        t, ends = norm_with_ends(title)
        best_len = 0
        found: set[int] = set()
        for k in self.keys:
            if len(k) < best_len:
                break
            if self._hit(t, ends, k):
                best_len = len(k)
                found |= self.index[k]
        if not found:
            return None, "상품명 → IGDB ID 매칭 실패"
        if len(found) > 1:
            return None, "상품명이 여러 게임과 같은 길이로 맞음 (확인 필요)"
        return next(iter(found)), ""

    @staticmethod
    def _hit(t: str, ends: set[int], k: str) -> bool:
        """k 가 t 안에 있고, 끝이 단어 경계이거나 뒤가 숫자·(영문 별칭이면) 영문자가 아니면 일치."""
        ascii_key = not HANGUL.search(k)
        start = t.find(k)
        while start != -1:
            end = start + len(k)
            nxt = t[end : end + 1]
            prev = t[start - 1 : start] if start else ""
            # 바로 뒤가 숫자: 붙어 있거나(하데스2) 떨어진 1~2자리(하데스 2)면 후속작.
            # 떨어진 3자리 이상(상품 코드, 연도 2018)은 괜찮다.
            num = re.match(r"\d+", t[end:])
            ok = not num or (end in ends and len(num.group()) >= 3)
            if ascii_key:
                if end not in ends and nxt.isascii() and nxt.isalpha():
                    ok = False
                if start not in ends and prev.isascii() and prev.isalpha():
                    ok = False
            if ok:
                return True
            start = t.find(k, start + 1)
        return False


def match_payload(title: str, matcher: TitleMatcher) -> tuple[int | None, str]:
    """거르기 → 이름 매칭. (game_id, 실패 이유)."""
    reason = exclude_reason(title)
    if reason:
        return None, reason
    return matcher.match(title)


def maps_matcher(maps: Any) -> TitleMatcher:
    """Maps.alias 로 만든 매처 (별칭 수가 바뀌면 다시 만든다)."""
    m = getattr(maps, "_title_matcher", None)
    if m is None or m.size != len(maps.alias):
        m = TitleMatcher(maps.alias)
        maps._title_matcher = m
    return m
