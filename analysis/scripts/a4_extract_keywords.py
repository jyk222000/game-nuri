"""A4 긍정·불만 유형: ES `reviews`에서 게임별 키워드를 뽑아 TSV로 저장한다.

서버(예: elk 또는 ES에 접속되는 VM)에서 한 번 실행한다. 표준 라이브러리만 쓴다.
리뷰 원문은 가져오지 않고 집계(키워드·건수)만 받는다.

실행 (비밀번호는 프롬프트로 입력):
    python3 analysis/scripts/a4_extract_keywords.py
    python3 analysis/scripts/a4_extract_keywords.py --limit 20     # 맛보기 20개
    # 저장소 없이 서버에서 단독 실행할 때
    python3 a4_extract_keywords.py --games-file /tmp/games_1000.csv --out-dir /tmp/a4
출력:
    analysis/data/a4_keywords.tsv    게임별·쪽별 키워드와 리뷰 건수
    analysis/data/a4_top_global.tsv  전체 리뷰 기준 명사 상위 (사전 보강용)

쿼리 방식은 collector/review_summary.py(기능 ⑤)와 같다.
  - 긍정 리뷰에서 부정 리뷰보다 두드러지게 자주 나온 명사 = 칭찬 키워드
  - 부정 리뷰에서 긍정 리뷰보다 두드러지게 자주 나온 명사 = 불만 키워드
"""

from __future__ import annotations

import argparse
import base64
import csv
import getpass
import json
import os
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GAMES_FILE = ROOT / "analysis" / "game_list" / "games_1000.csv"
OUT_DIR = ROOT / "analysis" / "data"
INDEX = "reviews"
LANGUAGE = "koreana"
MIN_REVIEWS = 30  # 리뷰가 이보다 적은 게임은 키워드가 믿을 만하지 않아 뺀다
KW_SIZE = 60  # 쪽(긍정·부정)마다 받을 키워드 수
PROS_MIN_DOC, CONS_MIN_DOC = 5, 3
PAUSE = 0.2


def post(url: str, body: dict, auth: str | None) -> dict:
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}
    )
    if auth:
        req.add_header("Authorization", "Basic " + auth)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def sig(side: bool, scope: dict) -> dict:
    opposite = {"bool": {"filter": [scope, {"term": {"voted_up": not side}}]}}
    return {
        "filter": {"term": {"voted_up": side}},
        "aggs": {
            "kw": {
                "significant_terms": {
                    "field": "review.nouns",
                    "size": KW_SIZE,
                    "min_doc_count": PROS_MIN_DOC if side else CONS_MIN_DOC,
                    "background_filter": opposite,
                    "chi_square": {"background_is_superset": False, "include_negatives": False},
                }
            }
        },
    }


def game_query(appid: int) -> dict:
    scope = {
        "bool": {"filter": [{"term": {"steam_appid": appid}}, {"term": {"language": LANGUAGE}}]}
    }
    return {
        "size": 0,
        "track_total_hits": True,
        "query": scope,
        "aggs": {
            "votes": {"terms": {"field": "voted_up"}},
            "pros": sig(True, scope),
            "cons": sig(False, scope),
        },
    }


def global_query(side: bool, size: int) -> dict:
    return {
        "size": 0,
        "query": {
            "bool": {"filter": [{"term": {"language": LANGUAGE}}, {"term": {"voted_up": side}}]}
        },
        "aggs": {"kw": {"terms": {"field": "review.nouns", "size": size}}},
    }


def read_games(path: Path, limit: int | None) -> list[tuple[int, int]]:
    out, seen = [], set()
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            gid, app = (row.get("game_id") or "").strip(), (row.get("steam_appid") or "").strip()
            if gid.isdigit() and app.isdigit() and int(gid) not in seen:
                seen.add(int(gid))
                out.append((int(gid), int(app)))
    return out[:limit] if limit else out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--es-url", default=os.environ.get("ES_URL", "http://elk:9200"))
    ap.add_argument("--user", default=os.environ.get("ES_USER", "elastic"))
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--games-file", type=Path, default=GAMES_FILE)
    ap.add_argument("--out-dir", type=Path, default=OUT_DIR)
    ap.add_argument("--global-size", type=int, default=200)
    a = ap.parse_args()

    pw = os.environ.get("ES_PASSWORD") or getpass.getpass(f"ES 비밀번호({a.user}): ")
    auth = base64.b64encode(f"{a.user}:{pw}".encode()).decode()
    base = a.es_url.rstrip("/") + f"/{INDEX}/_search"
    out_dir = a.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1) 전체 리뷰 기준 명사 상위 (사전 보강용)
    with open(out_dir / "a4_top_global.tsv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(["side", "keyword", "doc_count"])
        for side, name in ((True, "positive"), (False, "negative")):
            res = post(base, global_query(side, a.global_size), auth)
            for b in res["aggregations"]["kw"]["buckets"]:
                w.writerow([name, b["key"], b["doc_count"]])
    print("전체 상위 명사 저장")

    # 2) 게임별 키워드
    games = read_games(a.games_file, a.limit)
    kept = 0
    with open(out_dir / "a4_keywords.tsv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(
            [
                "game_id",
                "steam_appid",
                "total",
                "positive",
                "negative",
                "side",
                "keyword",
                "doc_count",
                "score",
            ]
        )
        for i, (gid, app) in enumerate(games, 1):
            try:
                res = post(base, game_query(app), auth)
            except Exception as e:  # 한 게임이 실패해도 계속
                print(f"[{i}/{len(games)}] game_id={gid} 실패: {e}")
                continue
            total = int(res["hits"]["total"]["value"])
            if total >= MIN_REVIEWS:
                votes = {
                    int(b["key"]): int(b["doc_count"])
                    for b in res["aggregations"]["votes"]["buckets"]
                }
                pos, neg = votes.get(1, 0), votes.get(0, 0)
                for side, key in (("positive", "pros"), ("negative", "cons")):
                    for b in res["aggregations"][key]["kw"]["buckets"]:
                        w.writerow(
                            [
                                gid,
                                app,
                                total,
                                pos,
                                neg,
                                side,
                                b["key"],
                                b["doc_count"],
                                round(b.get("score", 0), 4),
                            ]
                        )
                kept += 1
            if i % 50 == 0:
                print(f"[{i}/{len(games)}] 리뷰 {MIN_REVIEWS}건 이상 게임 {kept}개")
            time.sleep(PAUSE)
    print(f"끝: 게임 {len(games)}개 중 {kept}개 저장 → {out_dir / 'a4_keywords.tsv'}")


if __name__ == "__main__":
    main()
