"""게임 목록 CSV → 시작 대응표 JSON (ID_MAP_PATH 용).

    python -m refiner.build_id_map --csv games.csv --out id_map.json [--base id_map.json]

CSV 열 (첫 줄은 머리글, 빈 칸 허용):
    igdb_id, steam_appid, itad_id, name, name_ko, aliases
    - igdb_id 는 필수 (게임 기준 ID). 열 이름이 game_id 여도 된다
      (analysis/game_list/games_1000.csv)
    - aliases 는 다나와 상품명 매칭용 별칭을 | 로 구분 (예: 엘든링|엘든 링 PS5)
--base 를 주면 그 대응표에 덧붙인다 (이미 있는 값은 바꾸지 않는다).
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from refiner.router import Maps
from refiner.rules.normalize_title import normalize_title


def rows_to_maps(rows: list[dict[str, str]]) -> tuple[Maps, list[str]]:
    """CSV 행 → (대응표, 경고 목록). 같은 키가 다른 게임을 가리키면 먼저 나온 것을 쓴다."""
    m = Maps()
    warnings: list[str] = []

    def put(table: dict[Any, int], key: Any, gid: int, label: str) -> None:
        if key in (None, ""):
            return
        if key in table and table[key] != gid:
            warnings.append(f"{label} {key}: {table[key]} 와 {gid} 가 겹침 → {table[key]} 유지")
            return
        table[key] = gid

    for i, r in enumerate(rows, start=2):
        raw_id = (r.get("igdb_id") or r.get("game_id") or "").strip()
        if not raw_id.isdigit():
            warnings.append(f"{i}행: igdb_id 없음 → 건너뜀")
            continue
        gid = int(raw_id)
        appid = (r.get("steam_appid") or "").strip().removeprefix("app/")
        if appid.isdigit():
            put(m.steam, int(appid), gid, "steam")
        put(m.itad, (r.get("itad_id") or "").strip(), gid, "itad")
        names = [r.get("name"), r.get("name_ko"), *(r.get("aliases") or "").split("|")]
        for n in names:
            if n and n.strip():
                put(m.alias, normalize_title(n.strip()), gid, "alias")
    return m, warnings


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="게임 목록 CSV → 대응표 JSON")
    ap.add_argument("--csv", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--base", help="덧붙일 기존 대응표 JSON")
    a = ap.parse_args(argv)
    with open(a.csv, encoding="utf-8-sig", newline="") as f:
        maps, warnings = rows_to_maps(list(csv.DictReader(f)))
    if a.base:
        base = Maps(json.loads(Path(a.base).read_text(encoding="utf-8")))
        base.merge(maps)
        maps = base
    Path(a.out).write_text(
        json.dumps(maps.to_dict(), ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    for w in warnings:
        print("경고:", w)
    print(f"대응표 {maps.size()} → {a.out}")


if __name__ == "__main__":
    main()
