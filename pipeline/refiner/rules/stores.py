"""ITAD 판매처(shop) → refined.stores. 순수 함수 (docs/contracts/messages/refined.stores.json).

가격(raw.price)·가격 이력(raw.price kind=price_history)에 들어 있는 shop {id, name}으로
stores 한 줄을 만든다. 코드는 price.store_code()와 같아서 가격 표의 store와 항상 맞는다.
display_name: 8곳은 정해 둔 이름(시드와 같음), 나머지는 ITAD 이름. platform: ITAD 판매처라 pc.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from refiner.rules.price import store_code

DISPLAY_NAMES: dict[str, str] = {  # erd.sql 시드와 같다 (upsert 때 이름이 바뀌지 않게)
    "steam": "Steam",
    "epic": "Epic Games Store",
    "gog": "GOG",
    "msstore": "Microsoft Store",
    "blizzard": "Battle.net",
    "ea": "EA app",
    "ubisoft": "Ubisoft Store",
}

REFINED_STORE_SCHEMA: dict[str, Any] = {
    "type": "struct",
    "name": "refined_store",
    "fields": [
        {"field": "store", "type": "string", "optional": False},
        {"field": "display_name", "type": "string", "optional": False},
        {"field": "platform", "type": "string", "optional": False},
        {"field": "itad_shop_id", "type": "int32", "optional": True},
    ],
}


def store_row(shop: dict[str, Any]) -> dict[str, Any] | None:
    """shop {id, name} → stores 한 줄. 이름도 번호도 없으면 None."""
    sid, name = shop.get("id"), str(shop.get("name") or "").strip()
    if sid is None and not name:
        return None
    code = store_code(shop)
    return {
        "store": code,
        "display_name": DISPLAY_NAMES.get(code) or name or code,
        "platform": "pc",
        "itad_shop_id": int(sid) if str(sid).isdigit() else None,
    }


def shops_in(payload: Any) -> list[dict[str, Any]]:
    """ITAD 가격 응답(deals[].shop)·가격 이력(history[].shop, 또는 목록 그대로)에서 판매처 목록."""
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        items = list(payload.get("deals") or []) + list(payload.get("history") or [])
    else:
        items = []
    out = []
    for item in items:
        shop = item.get("shop") if isinstance(item, dict) else None
        if isinstance(shop, dict):
            out.append(shop)
    return out


def store_messages(
    shops: Iterable[dict[str, Any]], sent: set[str]
) -> list[tuple[str, str, dict[str, Any]]]:
    """처음 보는 판매처만 (실행마다 판매처별 한 번). sent 는 이미 보낸 store 코드."""
    out = []
    for shop in shops:
        row = store_row(shop)
        if row is None or row["store"] in sent:
            continue
        sent.add(row["store"])
        out.append(("stores", row["store"], {"schema": REFINED_STORE_SCHEMA, "payload": row}))
    return out
