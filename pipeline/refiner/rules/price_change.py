"""지금 가격이 지난번과 달라졌는지 기억한다 → 달라졌을 때만 price_history 로.

키 = prices_current PK (game_id, store, edition, platform, item_condition).
비교 값 = (원래 통화 가격, 통화, 정가 원화). 원화 환산값(price_krw)은 환율이 달마다 바뀌어서
가격이 그대로여도 달라지므로 비교에 쓰지 않는다 (원화 상점은 원래 값 = 원화).
처음 보는 키도 '바뀐 것'으로 본다 (이력의 첫 점).
상태는 main 이 PRICE_STATE_PATH 파일에 저장해 재시작해도 이어진다.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from refiner.rules.price import price_key


def _sig(row: dict[str, Any]) -> list[Any]:
    original = row.get("price_original")
    return [
        original if original is not None else row.get("price_krw"),
        row.get("currency_original") or "KRW",
        row.get("regular_krw"),
    ]


class LastPrices:
    def __init__(self, data: dict[str, list[Any]] | None = None):
        self.last: dict[str, list[Any]] = dict(data or {})
        self.changed = False

    @classmethod
    def load(cls, path: str | None) -> LastPrices:
        if path and Path(path).exists():
            return cls(json.loads(Path(path).read_text(encoding="utf-8")))
        return cls()

    def save(self, path: str | None) -> None:
        """바뀐 것이 있으면 저장 (임시 파일에 쓰고 바꿔 끼운다)."""
        if not path or not self.changed:
            return
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_text(json.dumps(self.last, ensure_ascii=False), encoding="utf-8")
        tmp.replace(p)
        self.changed = False

    def is_new(self, row: dict[str, Any]) -> bool:
        """처음 보거나 지난번과 다르면 True 를 돌려주고 기억한다."""
        k = ":".join(str(v) for v in price_key(row))
        sig = _sig(row)
        if self.last.get(k) == sig:
            return False
        self.last[k] = sig
        self.changed = True
        return True
