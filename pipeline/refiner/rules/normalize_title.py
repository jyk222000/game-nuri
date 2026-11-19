"""다나와 상품명 → 게임 이름 정규화 (순수 함수)."""

import re

NOISE = [
    r"\bPS[45]\b",
    r"\bSWITCH\b",
    r"스위치",
    r"닌텐도",
    r"XBOX[^ ]*",
    r"한글판",
    r"한국어판",
    r"초회한정",
    r"일반판",
    r"디럭스",
    r"에디션",
    r"\(.*?\)",
    r"\[.*?\]",
    r"SONY",
    r"소니",
]


def normalize_title(name: str) -> str:
    s = name.upper()
    for p in NOISE:
        s = re.sub(p, " ", s, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", s).strip()
