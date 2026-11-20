# ruff: noqa  -- 수집 가능성 시험용 일회성 스크립트(NW2-83). 운영 코드 아님
"""Gemini 로 영어 게임 이름의 한국어 표기 후보를 만든다(눈가림 시험).

보내는 것: 영어 게임 이름(+ 후보는 출시연도)만. 다나와 상품명·가격·키 값은 보내지 않는다.
키: .env 의 GEMINI_API_DANAWA_NAME_GENERATE_KEY (헤더로만 전달, 출력·저장하지 않음).
저장: samples/check_llm_names/gemini_proposed.json (check_llm_names.py 입력과 같은 형식), gemini_raw.json(응답 원본)
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_candidates as cc  # noqa: E402

load_dotenv(cc.ROOT / ".env")
KEY = os.environ["GEMINI_API_DANAWA_NAME_GENERATE_KEY"]
MODEL = "gemini-3.5-flash-lite"
URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
OUT = cc.ROOT / "samples" / "check_llm_names"
SIBLING_CANDIDATES = ["엘든 링", "갓 오브 워", "할로우 나이트", "하데스"]

PROMPT = """다음 비디오 게임의 영어 이름마다, 한국 온라인 쇼핑몰·게임 커뮤니티에서 쓰일 만한 한국어 표기 변형을 모두 알려 줘.
공식 한국어 이름이 있으면 그것을 먼저 쓰고, 음차 표기, 띄어쓰기 변형, 흔한 줄임말도 포함해 줘. 숫자·로마 숫자는 그대로 두거나 아라비아 숫자로 바꾼 표기를 둘 다 써 줘.
이름마다 3~8개. 모르는 게임이면 빈 배열을 줘. 지어내지 마.
출력은 JSON 객체 하나만: {{"영어 이름": ["한국어 표기", ...]}}

게임 목록:
{lines}
"""


CACHE_FILE = OUT / "gemini_cache.json"
_CACHE = json.loads(CACHE_FILE.read_text(encoding="utf-8")) if CACHE_FILE.exists() else {}


def ask(names: list[str]) -> dict:
    ck = json.dumps(names, ensure_ascii=False)
    if ck in _CACHE:
        return _CACHE[ck]
    r = _ask(names)
    _CACHE[ck] = r
    cc.save_json(CACHE_FILE, _CACHE)
    return r


def _ask(names: list[str]) -> dict:
    body = {
        "contents": [
            {"parts": [{"text": PROMPT.format(lines="\n".join(f"- {n}" for n in names))}]}
        ],
        "generationConfig": {
            "temperature": 0.2,
            "responseMimeType": "application/json",
            "maxOutputTokens": 16000,
        },
    }
    for attempt in range(6):
        r = requests.post(
            URL,
            headers={"x-goog-api-key": KEY, "Content-Type": "application/json"},
            json=body,
            timeout=180,
        )
        if r.status_code in (429, 500, 503):
            print(
                f"  HTTP {r.status_code}, {30 * (attempt + 1)}초 후 재시도: {r.text[:160].replace(KEY, '***')!r}",
                flush=True,
            )
            time.sleep(30 * (attempt + 1))
            continue
        if r.status_code != 200:
            raise RuntimeError(f"Gemini HTTP {r.status_code}: {r.text[:200].replace(KEY, '***')}")
        j = r.json()
        text = "".join(p.get("text", "") for p in j["candidates"][0]["content"]["parts"])
        try:
            parsed = json.loads(text)
        except ValueError:
            time.sleep(5)
            continue
        return {"raw": text, "usage": j.get("usageMetadata", {}), "parsed": parsed}
    raise RuntimeError("Gemini 429 반복")


def main():
    res = json.loads((cc.ROOT / "samples/check_candidates/result.json").read_text(encoding="utf-8"))
    own_in = []
    for c in cc.CANDIDATES:
        y = c.get("year")
        own_in.append(f"{c['en']} ({y}년작)" if y else c["en"])
    raw_log = {"model": MODEL, "calls": []}
    proposed = {
        "_note": f"{MODEL} 이 영어 이름만 보고 만든 한국어 표기 후보(눈가림). 입력에 다나와 표기 없음.",
        "own": {},
        "siblings": {},
    }

    # 후보 15개: 5개씩 3번
    answers: dict[str, list[str]] = {}
    for i in range(0, len(own_in), 5):
        r = ask(own_in[i : i + 5])
        raw_log["calls"].append(
            {
                "kind": "own",
                "input": own_in[i : i + 5],
                "usage": r["usage"],
                "response": r["parsed"],
            }
        )
        answers.update(r["parsed"])
        time.sleep(8)
    for c, label in zip(cc.CANDIDATES, own_in):
        proposed["own"][c["ko"]] = answers.get(label) or answers.get(c["en"]) or []

    # 시리즈 다른 게임: 4개 후보의 IGDB 대표 이름
    for idx, c in enumerate(cc.CANDIDATES, 1):
        if c["ko"] not in SIBLING_CANDIDATES:
            continue
        auto = json.loads(
            next((cc.ROOT / "samples/check_exclude_auto").glob(f"{idx:02d}_*.json")).read_text(
                encoding="utf-8"
            )
        )
        names = sorted({e["name"] for e in auto["auto_exclusions"]})
        merged = []
        for j in range(0, len(names), 8):
            part = names[j : j + 8]
            r = ask(part)
            raw_log["calls"].append(
                {
                    "kind": "siblings",
                    "candidate": c["ko"],
                    "input": part,
                    "usage": r["usage"],
                    "response": r["parsed"],
                }
            )
            for n in part:
                merged.extend(r["parsed"].get(n, []))
            time.sleep(8)
        proposed["siblings"][c["ko"]] = sorted(set(merged))

    cc.save_json(OUT / "gemini_proposed.json", proposed)
    cc.save_json(OUT / "gemini_raw.json", raw_log)
    for k, v in proposed["own"].items():
        print(f"{k}: {v}")
    for k, v in proposed["siblings"].items():
        print(f"[시리즈] {k}: {len(v)}개")


if __name__ == "__main__":
    main()
