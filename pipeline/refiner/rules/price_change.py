"""지금 가격이 지난번과 달라졌는지 기억한다 → 달라졌을 때만 price_history 로.

키 = prices_current PK (game_id, store, edition, platform, item_condition).
비교 값 = (원래 통화 가격, 통화, 정가 원화). 원화 환산값(price_krw)은 환율이 달마다 바뀌어서
가격이 그대로여도 달라지므로 비교에 쓰지 않는다 (원화 상점은 원래 값 = 원화).
처음 보는 키도 '바뀐 것'으로 본다 (이력의 첫 점).
상태는 main 이 PRICE_STATE_PATH 파일에 저장해 재시작해도 이어진다.

다나와 에디션(#93): console_keep() 이 같은 키에서 본편·에디션 중 무엇을 실을지 정한다.
  - 본편을 한 번이라도 봤으면 그 키의 에디션은 싣지 않는다 (본편 최저가를 왜곡하지 않게)
  - 본편이 없으면 에디션을 싣고, 같은 수집 회차 안에서는 더 싼 것만 싣는다
  - 같은 키라 prices_current 에서는 나중에 온 본편이 에디션 줄을 덮어쓴다 (upsert)
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from refiner.rules.price import price_key


def _sig(row: dict[str, Any]) -> list[Any]:
    original = row.get("price_original")
    return [
        original if original is not None else row.get("price_krw"),
        row.get("currency_original") or "KRW",
        row.get("regular_krw"),
        row.get("variant_name"),
    ]


def collect_round(collected_at: str | None) -> str:
    """다나와 수집 회차. 타이머가 KST 00·06·12·18시 30분에 시작해 2~3시간 돈다.

    UTC 로 3시간 30분을 빼면 시작 시각이 6시간 칸의 처음에 온다 → "날짜/칸".
    """
    try:
        t = datetime.fromisoformat(str(collected_at).replace("Z", "+00:00"))
    except ValueError:
        return str(collected_at or "")[:13]
    t -= timedelta(hours=3, minutes=30)
    return f"{t.date().isoformat()}/{t.hour // 6}"


class LastPrices:
    def __init__(
        self,
        data: dict[str, list[Any]] | None = None,
        picks: dict[str, list[Any]] | None = None,
    ):
        self.last: dict[str, list[Any]] = dict(data or {})
        # 다나와 키 → [에디션이면 1 본편이면 0, 가격, 수집 회차]
        self.picks: dict[str, list[Any]] = dict(picks or {})
        self.changed = False

    @classmethod
    def load(cls, path: str | None) -> LastPrices:
        if path and Path(path).exists():
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            if isinstance(data.get("last"), dict):  # 11/24 이후 형식
                return cls(data["last"], data.get("picks"))
            return cls(data)  # 예전 형식 = last 만
        return cls()

    def save(self, path: str | None) -> None:
        """바뀐 것이 있으면 저장 (임시 파일에 쓰고 바꿔 끼운다)."""
        if not path or not self.changed:
            return
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + ".tmp")
        doc = {"last": self.last, "picks": self.picks}
        tmp.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
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

    def console_keep(self, row: dict[str, Any]) -> bool:
        """다나와 한 줄을 실을지. 본편 > 에디션, 같은 회차면 더 싼 것 (#93)."""
        k = ":".join(str(v) for v in price_key(row))
        tier = 1 if row.get("variant_name") else 0
        price = row["price_krw"]
        rnd = collect_round(row.get("collected_at"))
        prev = self.picks.get(k)
        if prev is not None:
            p_tier, p_price, p_rnd = prev
            if tier > p_tier:
                return False  # 본편을 본 적이 있으면 에디션은 싣지 않는다
            if tier == p_tier and p_rnd == rnd and price >= p_price:
                return False  # 같은 회차에 같은 종류로 더 싼 것이 이미 있음
        self.picks[k] = [tier, price, rnd]
        self.changed = True
        return True
