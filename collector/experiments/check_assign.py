# ruff: noqa  -- 수집 가능성 시험용 일회성 스크립트(NW2-83). 운영 코드 아님
"""상품→게임 배정 시험(외부 호출 없음). 수동 제외 규칙 대신 '시리즈를 함께 색인해 가장 잘 맞는 게임에 배정'한다.

색인(문서): 후보 게임 1개 + 같은 시리즈의 다른 게임들(IGDB). 문서마다 이름 키 목록을 가진다.
점수: 상품명에서 찾은 이름 키 중 가장 긴 것의 길이(엘라스틱서치의 '더 구체적으로 맞을수록 높은 점수'를 단순화).
배정: 점수가 가장 높은 문서. 후보가 아닌 문서에 배정된 상품은 버린다. 후보와 다른 문서가 점수가 같으면 '확인 필요'.
이름 키 출처 두 가지를 비교한다.
  A: IGDB(영어 이름·대체 이름·한국어 현지화) + 후보의 한국어 이름·별칭
  B: A + Gemini 가 만든 표기(자신 이름·시리즈 이름)
평가: 수동 danawa_exclude 가 있는 4개 후보에서 수동 규칙과 비교, 나머지 11개는 배정이 버린 상품을 눈으로 확인할 수 있게 출력.
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
gem = json.loads(
    (ROOT / "samples/check_llm_names/gemini_proposed.json").read_text(encoding="utf-8")
)


def load(idx):
    parsed = json.loads(
        next((ROOT / "samples/check_candidates/danawa").glob(f"{idx:02d}_*_parsed.json")).read_text(
            encoding="utf-8"
        )
    )
    auto = json.loads(
        next((ROOT / "samples/check_exclude_auto").glob(f"{idx:02d}_*.json")).read_text(
            encoding="utf-8"
        )
    )
    return parsed, auto


def build_docs(c, parsed, auto, with_gemini: bool):
    own_names = list(parsed.get("match_names") or [c["ko"], c["en"]])
    docs = {"__candidate__": list(own_names)}
    if with_gemini:
        docs["__candidate__"] += gem["own"].get(c["ko"], [])
    for e in auto["auto_exclusions"]:
        docs[f"sib:{e['id']}:{e['name']}"] = list(e["names"])
    for e in auto["same_name_siblings"]:  # 대표 이름이 후보와 같은 다른 항목(원작·리메이크 등)
        docs[f"same:{e['id']}:{e['name']}"] = list(e["names"])
    if with_gemini:
        extra = gem["siblings"].get(c["ko"], [])
        if extra:
            docs["gemini_siblings"] = list(extra)
    return docs


def score(title: str, keys: list[str]) -> int:
    t = n2(title)
    best = 0
    for n in keys:
        k = n2(n)
        if len(k) >= 3 and has_key(t, k):
            best = max(best, len(k))
    return best


def assign(title: str, docs: dict) -> tuple[str | None, bool]:
    scores = {d: score(title, ks) for d, ks in docs.items()}
    top = max(scores.values())
    if top == 0:
        return None, False
    winners = [d for d, s in scores.items() if s == top]
    cand = "__candidate__" in winners
    # 'same:' 문서는 후보와 이름이 같은 다른 IGDB 항목(포트·중복 등)이라 충돌로 보지 않는다. 다른 게임(sib:)과 같은 점수일 때만 충돌.
    others = [w for w in winners if w.startswith("sib:") or w == "gemini_siblings"]
    if cand and others:
        return "__candidate__", True  # 후보와 같은 점수의 다른 문서: 동명 충돌, 확인 필요
    return (winners[0] if not winners[0].startswith("same:") else "__candidate__"), False


def run(with_gemini: bool):
    label = "B(IGDB+Gemini)" if with_gemini else "A(IGDB만)"
    print(f"\n######## 배정 방식 {label} ########")
    tot = {"both": 0, "assign_only": 0, "manual_only": 0, "conflict": 0}
    for idx, c in enumerate(cc.CANDIDATES, 1):
        parsed, auto = load(idx)
        docs = build_docs(c, parsed, auto, with_gemini)
        manual = c.get("danawa_exclude")
        items = [
            it
            for it in parsed["items"]
            if it.get("name_match")
            and it["source"] in ("catalog", "shop_listing")
            and it.get("is_game") is not False
        ]
        both = a_only = m_only = conflict = 0
        a_titles, m_titles = [], []
        for it in items:
            text = f"{it['title']} {it.get('bundle') or ''}"
            d, tie = assign(text, docs)
            dropped = d is not None and d != "__candidate__"
            conflict += tie
            m = bool(manual and re.search(manual, text, re.I))
            if m and dropped:
                both += 1
            elif dropped:
                a_only += 1
                a_titles.append(f"{it['title'][:55]} → {d.split(':', 2)[-1]}")
            elif m:
                m_only += 1
                m_titles.append(it["title"][:60])
        for k, v in zip(
            ("both", "assign_only", "manual_only", "conflict"), (both, a_only, m_only, conflict)
        ):
            tot[k] += v
        tag = "수동규칙 있음" if manual else "수동규칙 없음"
        print(
            f"  {c['ko']}({tag}): 상품 {len(items)}건 | 배정이 버림∩수동 {both}, 배정만 버림 {a_only}, 수동만 버림 {m_only}, 동명충돌(확인필요) {conflict}"
        )
        for t in a_titles[:4]:
            print("     배정만 버림:", t)
        if manual:
            real = [
                t for t in m_titles if not re.search(r"컨트롤러|스탠드|스티커|피규어|패드|장식", t)
            ]
            for t in real[:3]:
                print("     수동만 버림(비게임 제외):", t)
    print("  합계:", tot)


if __name__ == "__main__":
    run(False)
    run(True)
