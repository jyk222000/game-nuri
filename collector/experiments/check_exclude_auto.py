# ruff: noqa  -- 수집 가능성 시험용 일회성 스크립트(NW2-83). 운영 코드 아님
"""다나와 제외 규칙 자동 생성 시험.

방법: IGDB 에서 후보와 같은 시리즈(collections/franchises)의 다른 게임을 받아, 이름에 후보 이름이 들어 있고
더 긴 항목(후속작·스핀오프 등)의 이름(영문+한국어)을 제외 이름으로 만든다. 저장된 다나와 결과(samples/check_candidates)에
적용해 수동 danawa_exclude 와 비교한다. 새 다나와 요청은 없다. IGDB 호출만 한다(0.3초 간격은 Igdb 게이트가 처리).
저장: samples/check_exclude_auto/
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_candidates as cc  # noqa: E402

OUT = cc.ROOT / "samples" / "check_exclude_auto"
# 자동 제외 대상에서 빼는 종류: 에디션/번들/DLC/확장/버전은 EDITION_RULES 가 따로 처리하므로 같은 게임으로 본다.
# IGDB game_type: 0 main, 1 dlc, 2 expansion, 3 bundle, 4 standalone expansion, 5 mod, 6 episode, 7 season,
#                 8 remake, 9 remaster, 10 expanded game, 11 port, 12 fork, 13 pack, 14 update
SAME_GAME_TYPES = {1, 2, 3, 13, 14}


_ROMAN = {"ii": "2", "iii": "3", "iv": "4"}


def n2(s: str) -> str:
    """cc.norm + 로마 숫자(II/III/IV)를 아라비아 숫자로. '하데스 II' 와 '하데스2' 를 같게 본다."""
    s = re.sub(r"(?<![a-z])(iii|ii|iv)(?![a-z])", lambda m: _ROMAN[m.group(1)], s.lower())
    return cc.norm(s)


def has_key(text: str, key: str) -> bool:
    """key 가 text 에 들어 있는지. key 가 숫자로 끝나면 바로 뒤에 숫자가 이어지는 경우는 제외('갓오브워2' ≠ '갓오브워2018')."""
    start = 0
    while True:
        i = text.find(key, start)
        if i < 0:
            return False
        j = i + len(key)
        if not (key[-1].isdigit() and j < len(text) and text[j].isdigit()):
            return True
        start = i + 1


def chunks(xs, n):
    for i in range(0, len(xs), n):
        yield xs[i : i + n]


def related_games(igdb, gid: int) -> tuple[dict, list[dict]]:
    base = igdb.query(
        "games",
        f"fields name,game_type,first_release_date,collections.name,franchises.name,"
        f"version_parent,parent_game; where id = {gid};",
    )[0]
    col_ids = [c["id"] for c in base.get("collections", [])]
    fr_ids = [f["id"] for f in base.get("franchises", [])]
    conds = []
    if col_ids:
        conds.append(f"collections = ({','.join(map(str, col_ids))})")
    if fr_ids:
        conds.append(f"franchises = ({','.join(map(str, fr_ids))})")
    rel: dict[int, dict] = {}
    for cond in conds:
        off = 0
        while True:
            rows = igdb.query(
                "games",
                f"fields name,game_type,first_release_date,version_parent,parent_game; "
                f"where {cond} & id != {gid}; limit 500; offset {off};",
            )
            for r in rows:
                rel[r["id"]] = r
            if len(rows) < 500:
                break
            off += 500
    # 같은 이름 검색으로 시리즈에 안 묶인 항목도 보강(동명 원작·리메이크 등)
    for r in igdb.query(
        "games",
        f"fields name,game_type,first_release_date,version_parent,parent_game; "
        f'search "{base["name"]}"; where id != {gid}; limit 50;',
    ):
        rel.setdefault(r["id"], r)
    return base, list(rel.values())


def names_of(igdb, ids: list[int]) -> dict[int, list[str]]:
    out: dict[int, list[str]] = {i: [] for i in ids}
    for ch in chunks(ids, 50):
        lst = ",".join(map(str, ch))
        for r in igdb.query(
            "alternative_names", f"fields game,name; where game = ({lst}); limit 500;"
        ):
            if r.get("name"):
                out[r["game"]].append(r["name"])
        for r in igdb.query(
            "game_localizations", f"fields game,name; where game = ({lst}); limit 500;"
        ):
            if r.get("name"):
                out[r["game"]].append(r["name"])
    return out


def build_exclusions(
    base: dict, rel: list[dict], names: dict[int, list[str]], base_names: list[str]
):
    """제외 이름 목록과, 이름이 같아 이름만으로는 못 거르는 항목을 돌려준다."""
    base_keys = [n2(n) for n in base_names if n2(n)]
    excl, ambiguous, skipped = [], [], []
    for r in rel:
        gtype = r.get("game_type")
        if gtype in SAME_GAME_TYPES or r.get("version_parent") == base["id"]:
            skipped.append((r["name"], "에디션/DLC류"))
            continue
        all_names = [r["name"], *names.get(r["id"], [])]
        same = (
            [r["name"]] if n2(r["name"]) in base_keys else []
        )  # 대표 이름이 후보와 같은 항목만 '동명'
        longer = []
        for n in all_names:
            k = n2(n)
            if any(has_key(k, bk) and len(k) > len(bk) for bk in base_keys):
                longer.append(n)
        if same:
            ambiguous.append(
                {
                    "id": r["id"],
                    "name": r["name"],
                    "game_type": gtype,
                    "year": r.get("first_release_date"),
                    "names": sorted(set(all_names)),
                }
            )
        elif longer:
            excl.append(
                {"id": r["id"], "name": r["name"], "game_type": gtype, "names": sorted(set(longer))}
            )
    return excl, ambiguous, skipped


def main():
    load_dotenv(cc.ROOT / ".env")
    igdb = cc.Igdb(os.environ["IGDB_CLIENT_ID"], os.environ["IGDB_CLIENT_SECRET"])
    res = json.loads((cc.ROOT / "samples/check_candidates/result.json").read_text(encoding="utf-8"))
    rows = res["rows"]
    summary = []
    for idx, (c, row) in enumerate(zip(cc.CANDIDATES, rows), 1):
        gid = row.get("igdb_id")
        if not gid:
            continue
        slug = None
        for p in (cc.ROOT / "samples/check_candidates/danawa").glob(f"{idx:02d}_*_parsed.json"):
            slug = p
        base, rel = related_games(igdb, int(gid))
        nm = names_of(igdb, [r["id"] for r in rel]) if rel else {}
        parsed = (
            json.loads(slug.read_text(encoding="utf-8"))
            if slug
            else {"items": [], "match_names": []}
        )
        base_names = parsed.get("match_names") or [c["ko"], c["en"]]
        excl, amb, skipped = build_exclusions(base, rel, nm, base_names)
        auto_keys = [(n2(n), e["name"]) for e in excl for n in e["names"]]
        manual = c.get("danawa_exclude")
        mism = {"both": [], "manual_only": [], "auto_only": []}
        for it in parsed["items"]:
            if not it.get("name_match") or it["source"] not in ("catalog", "shop_listing"):
                continue
            if it.get("is_game") is False:  # 비게임 상품은 다른 필터가 이미 거른다
                continue
            text = f"{it['title']} {it.get('bundle') or ''}"
            m = bool(manual and re.search(manual, text, re.I))
            hit = next((src for k, src in auto_keys if k and has_key(n2(text), k)), None)
            if m and hit:
                mism["both"].append(it["title"])
            elif m:
                mism["manual_only"].append(it["title"])
            elif hit:
                mism["auto_only"].append(f"{it['title']}  ← {hit}")
        rec = {
            "candidate": c["ko"],
            "igdb_id": gid,
            "collections": [x["name"] for x in base.get("collections", [])],
            "franchises": [x["name"] for x in base.get("franchises", [])],
            "related_count": len(rel),
            "auto_exclusions": excl,
            "same_name_siblings": amb,
            "skipped_edition_like": len(skipped),
            "has_manual_rule": bool(manual),
            "compare": mism,
        }
        cc.save_json(OUT / f"{idx:02d}_{cc.norm(c['en'])}.json", rec)
        summary.append(rec)
        print(
            f"[{idx:02d}] {c['ko']}: 관련 {len(rel)}개, 자동 제외 이름 {len(excl)}건, 동명 {len(amb)}건 | "
            f"수동∩자동 {len(mism['both'])}, 수동만 {len(mism['manual_only'])}, 자동만 {len(mism['auto_only'])}"
        )
        for t in mism["manual_only"][:5]:
            print("     수동만(자동이 못 거름):", t)
        for t in mism["auto_only"][:5]:
            print("     자동만(수동엔 없음):", t)
        for a in amb[:3]:
            print("     동명 항목:", a["name"], a["game_type"], a["names"][:4])
    cc.save_json(OUT / "summary.json", summary)


if __name__ == "__main__":
    main()
