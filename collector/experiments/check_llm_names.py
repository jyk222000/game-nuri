# ruff: noqa  -- 수집 가능성 시험용 일회성 스크립트(NW2-83). 운영 코드 아님
"""LLM 이 만든 한국어 표기 후보(samples/check_llm_names/proposed.json)의 효과 시험. 외부 호출 없음.

own      : 후보의 한국어 표기 변형만으로 다나와 상품(한국어 이름으로 확정한 name_match 항목)을 얼마나 찾나
siblings : 시리즈 다른 게임의 한국어 표기로 수동 제외 규칙이 거른 상품을 얼마나 찾나 / 잘못 거른 것은 없나
비교 기준: IGDB 이름만 쓴 자동 규칙(check_exclude_auto)과 수동 규칙.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_candidates as cc  # noqa: E402
from check_exclude_auto import has_key, n2  # noqa: E402

ROOT = cc.ROOT
PROP_FILE = sys.argv[1] if len(sys.argv) > 1 else "proposed.json"
prop = json.loads((ROOT / "samples/check_llm_names" / PROP_FILE).read_text(encoding="utf-8"))


def items_of(idx):
    p = next((ROOT / "samples/check_candidates/danawa").glob(f"{idx:02d}_*_parsed.json"))
    return [
        it
        for it in json.loads(p.read_text(encoding="utf-8"))["items"]
        if it["source"] in ("catalog", "shop_listing") and it.get("is_game") is not False
    ]


def hit(text, names):
    t = n2(text)
    for n in names:
        k = n2(n)
        if k and has_key(t, k):
            return n
    return None


print("== own: 이름 변형 후보만으로 후보 상품 찾기 ==")
tot_f = tot_n = 0
for idx, c in enumerate(cc.CANDIDATES, 1):
    truth = [it for it in items_of(idx) if it.get("name_match")]
    names = prop["own"][c["ko"]]
    found = [it for it in truth if hit(it["title"], names)]
    miss = [it["title"][:50] for it in truth if it not in found]
    tot_f += len(found)
    tot_n += len(truth)
    print(f"  {c['ko']}: {len(found)}/{len(truth)}", "" if not miss else f" 놓침 예: {miss[:2]}")
print(f"  합계 {tot_f}/{tot_n} ({round(100 * tot_f / tot_n)}%)")

print("\n== siblings: 시리즈 다른 게임 한국어 표기로 제외 상품 찾기 ==")
for idx, c in enumerate(cc.CANDIDATES, 1):
    if c["ko"] not in prop["siblings"]:
        continue
    manual = c.get("danawa_exclude")
    igdb_auto = json.loads(
        next((ROOT / "samples/check_exclude_auto").glob(f"{idx:02d}_*.json")).read_text(
            encoding="utf-8"
        )
    )
    igdb_names = sorted({n for e in igdb_auto["auto_exclusions"] for n in e["names"]})
    names = prop["siblings"][c["ko"]]
    both = llm_only = man_only = 0
    gains, wrongs, misses = [], [], []
    for it in [i for i in items_of(idx) if i.get("name_match")]:
        text = f"{it['title']} {it.get('bundle') or ''}"
        m = bool(manual and re.search(manual, text, re.I))
        l = hit(text, names)
        ig = hit(text, igdb_names)
        if m and l:
            both += 1
        elif l:
            llm_only += 1
            (gains if not ig else wrongs).append(f"{it['title'][:55]} ← {l}")
        elif m:
            man_only += 1
            if not ig:
                misses.append(it["title"][:55])
    print(f"  {c['ko']}: 둘 다 {both}, LLM만 {llm_only}, 수동만 {man_only}")
    for t in gains[:6]:
        print("     LLM만(IGDB 자동도 못 잡음):", t)
    for t in wrongs[:4]:
        print("     LLM만(IGDB 자동은 잡음):", t)
    for t in misses[:5]:
        print("     수동만:", t)
