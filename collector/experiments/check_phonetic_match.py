# ruff: noqa  -- 수집 가능성 시험용 일회성 스크립트(NW2-83). 운영 코드 아님
"""발음 기준 느슨한 이름 비교 시험 (외부 호출 없음, 저장된 샘플만 사용).

영어 이름과 한글 상품명을 같은 '자음 뼈대'로 바꿔 편집 거리로 비교한다.
- 영어: 철자 규칙으로 자음만 남기고 비슷한 자음(b/p/f/v, d/t, g/k/c/q, l/r, s/z, j/ch)을 합친다.
- 한글: 자모로 분해해 같은 합치기 규칙을 쓴다(받침 ㄱㅋ→k, ㄴ→n, ㄹ→r, ㅁ→m, ㅂㅍ→p, ㅇ→n, 나머지→t).
숫자는 그대로 두고 정확히 맞아야 한다(로마 숫자는 아라비아 숫자로).

시험 3가지:
  T1 재현율: 영어 이름만으로 '이 후보 상품'(한국어 이름으로 확정한 name_match 항목)을 얼마나 찾나
  T2 오탐: 후보 A 의 영어 이름이 다른 후보 B 의 상품명에 걸리나
  T3 제외 이름: 같은 시리즈 다른 게임의 영어 이름으로, 수동 제외 규칙이 거른 상품을 찾나
저장: samples/check_phonetic/
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_candidates as cc  # noqa: E402

OUT = cc.ROOT / "samples" / "check_phonetic"
ROMAN = {"ii": "2", "iii": "3", "iv": "4"}

INI = {
    "ㄱ": "k",
    "ㄲ": "k",
    "ㅋ": "k",
    "ㄴ": "n",
    "ㄷ": "t",
    "ㄸ": "t",
    "ㅌ": "t",
    "ㄹ": "r",
    "ㅁ": "m",
    "ㅂ": "p",
    "ㅃ": "p",
    "ㅍ": "p",
    "ㅅ": "s",
    "ㅆ": "s",
    "ㅇ": "",
    "ㅈ": "s",
    "ㅉ": "s",
    "ㅊ": "s",
    "ㅎ": "h",
}
FIN = {
    "": "",
    "ㄱ": "k",
    "ㄲ": "k",
    "ㄳ": "k",
    "ㄴ": "n",
    "ㄵ": "n",
    "ㄶ": "n",
    "ㄷ": "t",
    "ㄹ": "r",
    "ㄺ": "r",
    "ㄻ": "m",
    "ㄼ": "r",
    "ㄽ": "r",
    "ㄾ": "r",
    "ㄿ": "r",
    "ㅀ": "r",
    "ㅁ": "m",
    "ㅂ": "p",
    "ㅄ": "p",
    "ㅅ": "t",
    "ㅆ": "t",
    "ㅇ": "n",
    "ㅈ": "t",
    "ㅊ": "t",
    "ㅋ": "k",
    "ㅌ": "t",
    "ㅍ": "p",
    "ㅎ": "t",
}
CHO = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
JONG = [
    "",
    "ㄱ",
    "ㄲ",
    "ㄳ",
    "ㄴ",
    "ㄵ",
    "ㄶ",
    "ㄷ",
    "ㄹ",
    "ㄺ",
    "ㄻ",
    "ㄼ",
    "ㄽ",
    "ㄾ",
    "ㄿ",
    "ㅀ",
    "ㅁ",
    "ㅂ",
    "ㅄ",
    "ㅅ",
    "ㅆ",
    "ㅇ",
    "ㅈ",
    "ㅊ",
    "ㅋ",
    "ㅌ",
    "ㅍ",
    "ㅎ",
]


def collapse(s: str) -> str:
    return re.sub(r"(.)\1+", r"\1", s)


def hangul_skel(ch: str) -> str:
    code = ord(ch) - 0xAC00
    ini, rest = divmod(code, 21 * 28)
    _, fin = divmod(rest, 28)
    return INI[CHO[ini]] + FIN[JONG[fin]]


def latin_skel(w: str) -> str:
    w = w.lower()
    for a, b in (
        ("tch", "s"),
        ("ph", "f"),
        ("ck", "k"),
        ("ch", "s"),
        ("sh", "s"),
        ("th", "s"),
        ("kn", "n"),
        ("gh", ""),
        ("wr", "r"),
        ("qu", "k"),
        ("ng", "n"),
        ("x", "ks"),
        ("wh", ""),
    ):
        w = w.replace(a, b)
    w = re.sub(r"c(?=[eiy])", "s", w)
    w = re.sub(
        r"r(?![aeiouy])", "", w
    )  # 모음 앞이 아닌 r 은 한국어 표기에서 보통 안 나온다(cyber→사이버, Hogwarts→호그와트)
    out = []
    for ch in w:
        if ch in "aeiouwy":
            continue
        out.append(
            {
                "b": "p",
                "f": "p",
                "v": "p",
                "p": "p",
                "d": "t",
                "t": "t",
                "g": "k",
                "k": "k",
                "c": "k",
                "q": "k",
                "l": "r",
                "r": "r",
                "s": "s",
                "z": "s",
                "j": "s",
                "m": "m",
                "n": "n",
                "h": "h",
            }.get(ch, ch if ch.isdigit() else "")
        )
    return "".join(out)


def skeleton_pos(text: str) -> tuple[str, set[int]]:
    """뼈대 문자열과 '단어가 시작하는 위치' 집합. 단어는 공백·기호로 나뉜 덩어리다."""
    t = re.sub(r"(?<![a-z])(iii|ii|iv)(?![a-z])", lambda m: ROMAN[m.group(1)], text.lower())
    out, starts, pos = [], {0}, 0
    for word in re.findall(r"[0-9a-z가-힣]+", t):
        parts = []
        for m in re.finditer(r"[가-힣]|[a-z]+|\d+", word):
            g = m.group(0)
            parts.append(
                hangul_skel(g) if "가" <= g[0] <= "힣" else g if g[0].isdigit() else latin_skel(g)
            )
        sk = collapse("".join(parts))
        if not sk:
            continue
        starts.add(pos)
        out.append(sk)
        pos += len(sk)
    return "".join(out), starts


def skeleton(text: str) -> str:
    return skeleton_pos(text)[0]


def approx_find(text: str, key: str, max_ed: int, starts: set[int] | None = None) -> int | None:
    """text 안에서 key 와 편집 거리 max_ed 이하로 맞는 부분 문자열의 최소 거리. key 가 숫자로 끝나면 바로 뒤가 숫자인 경우는 제외."""
    m, n = len(key), len(text)
    if m == 0:
        return None
    INF = 99
    prev = list(range(m + 1))  # prev[i]: key[:i] 를 맞추는 비용
    best = None
    for j in range(1, n + 1):
        cur = [0 if (starts is None or j in starts) else INF] + [0] * m
        for i in range(1, m + 1):
            cost = 0 if key[i - 1] == text[j - 1] else 1
            cur[i] = min(prev[i - 1] + cost, prev[i] + 1, cur[i - 1] + 1)
        if cur[m] <= max_ed:
            nxt = text[j] if j < n else ""
            if not (key[-1].isdigit() and nxt.isdigit()):
                best = cur[m] if best is None else min(best, cur[m])
        prev = cur
    return best


def allowed_ed(key: str) -> int:
    letters = len(re.sub(r"\d", "", key))
    return 0 if letters < 8 else 1


def fuzzy_hit(title: str, names: list[str]) -> str | None:
    t, starts = skeleton_pos(title)
    for n in names:
        k = skeleton(n)
        if len(re.sub(r"\d", "", k)) < 4:  # 뼈대가 너무 짧으면 비교하지 않는다
            continue
        if approx_find(t, k, allowed_ed(k), starts) is not None:
            return n
    return None


def load():
    res = json.loads((cc.ROOT / "samples/check_candidates/result.json").read_text(encoding="utf-8"))
    parsed = {}
    for idx in range(1, 16):
        p = next((cc.ROOT / "samples/check_candidates/danawa").glob(f"{idx:02d}_*_parsed.json"))
        parsed[idx] = json.loads(p.read_text(encoding="utf-8"))
    return res["rows"], parsed


def main():
    rows, parsed = load()
    keys = {}
    for idx, c in enumerate(cc.CANDIDATES, 1):
        keys[idx] = [v for v in cc.name_variants(c["en"]) if v]
    report = {"T1": [], "T2": [], "T3": []}

    print("== 뼈대 확인(한글 표기 vs 영어 이름) ==")
    for c in cc.CANDIDATES:
        print(f"  {c['ko']}: {skeleton(c['ko'])}  |  {c['en']}: {skeleton(c['en'])}")

    print("\n== T1 재현율: 영어 이름만으로 후보 상품 찾기 ==")
    for idx, c in enumerate(cc.CANDIDATES, 1):
        items = [
            it
            for it in parsed[idx]["items"]
            if it.get("name_match")
            and it["source"] in ("catalog", "shop_listing")
            and it.get("is_game") is not False
        ]
        hit = [it for it in items if fuzzy_hit(it["title"], keys[idx])]
        miss = [it["title"] for it in items if it not in hit]
        report["T1"].append(
            {"candidate": c["ko"], "n": len(items), "found": len(hit), "missed_examples": miss[:5]}
        )
        print(f"  {c['ko']}: {len(hit)}/{len(items)}", "" if not miss else f"  놓침 예: {miss[:2]}")

    print("\n== T2 오탐: 후보 A 의 영어 이름이 다른 후보 B 상품에 걸리나 ==")
    fp = 0
    for a, ca in enumerate(cc.CANDIDATES, 1):
        for b in range(1, 16):
            if a == b:
                continue
            for it in parsed[b]["items"]:
                if not it.get("name_match") or it.get("is_game") is False:
                    continue
                h = fuzzy_hit(it["title"], keys[a])
                if h:
                    fp += 1
                    report["T2"].append(
                        {
                            "key_of": ca["ko"],
                            "title_of": cc.CANDIDATES[b - 1]["ko"],
                            "title": it["title"],
                        }
                    )
                    if fp <= 12:
                        print(f"  {ca['ko']} ← [{cc.CANDIDATES[b - 1]['ko']}] {it['title'][:60]}")
    print("  오탐 건수:", fp)

    print("\n== T3 제외 이름: 시리즈 다른 게임의 영어 이름으로 수동 제외 상품을 찾나 ==")
    for idx, c in enumerate(cc.CANDIDATES, 1):
        manual = c.get("danawa_exclude")
        if not manual:
            continue
        auto = json.loads(
            next((cc.ROOT / "samples/check_exclude_auto").glob(f"{idx:02d}_*.json")).read_text(
                encoding="utf-8"
            )
        )
        sib_names = sorted({n for e in auto["auto_exclusions"] for n in e["names"]})
        items = [
            it
            for it in parsed[idx]["items"]
            if it.get("name_match")
            and it["source"] in ("catalog", "shop_listing")
            and it.get("is_game") is not False
        ]
        both = fz_only = man_only = 0
        fz_only_titles, man_only_titles = [], []
        for it in items:
            text = f"{it['title']} {it.get('bundle') or ''}"
            m = bool(re.search(manual, text, re.I))
            h = fuzzy_hit(text, sib_names)
            if m and h:
                both += 1
            elif h:
                fz_only += 1
                fz_only_titles.append(f"{it['title'][:50]} ← {h}")
            elif m:
                man_only += 1
                man_only_titles.append(it["title"][:60])
        report["T3"].append(
            {
                "candidate": c["ko"],
                "both": both,
                "fuzzy_only": fz_only,
                "manual_only": man_only,
                "fuzzy_only_titles": fz_only_titles,
                "manual_only_titles": man_only_titles,
            }
        )
        print(f"  {c['ko']}: 둘 다 {both}, 퍼지만 {fz_only}, 수동만 {man_only}")
        for t in fz_only_titles[:6]:
            print("     퍼지만:", t)
        for t in man_only_titles[:4]:
            print("     수동만:", t)
    cc.save_json(OUT / "report.json", report)


if __name__ == "__main__":
    main()
