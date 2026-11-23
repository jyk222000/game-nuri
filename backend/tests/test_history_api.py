"""#11 가격 이력: 기간·필터, 같은 (game, store, edition, platform, 상태, 시각) 중복 제거."""

from datetime import UTC, datetime, timedelta

from app.db.models import PriceHistory
from app.services.history import dedupe

from tests.conftest import seed

NOW = datetime.now(UTC).replace(tzinfo=None, microsecond=0)


def _h(id_, days_ago, price, store="steam", edition="digital", platform="PC", cond="new"):
    return PriceHistory(
        id=id_,
        game_id=119133,
        store=store,
        edition=edition,
        platform=platform,
        item_condition=cond,
        price_krw=price,
        regular_krw=64800,
        discount_pct=10,
        collected_at=NOW - timedelta(days=days_ago),
    )


def test_history_defaults_and_period(env) -> None:
    client, engine, _ = env
    with seed(engine) as s:
        s.add_all([_h(1, 10, 50000), _h(2, 200, 40000), _h(3, 1, 47900)])
    body = client.get("/api/games/119133/history").json()
    assert body["days"] == 180 and body["platform"] is None and body["item_condition"] is None
    assert [i["price_krw"] for i in body["items"]] == [50000, 47900]  # 200일 전은 제외, 오래된 순
    assert set(body["items"][0]) == {
        "store",
        "edition",
        "platform",
        "item_condition",
        "collected_at",
        "price_krw",
        "regular_krw",
        "discount_pct",
    }
    assert body["items"][0]["collected_at"].endswith("Z")

    wide = client.get("/api/games/119133/history?days=365").json()
    assert [i["price_krw"] for i in wide["items"]] == [40000, 50000, 47900]


def test_history_filters(env) -> None:
    client, engine, _ = env
    with seed(engine) as s:
        s.add_all(
            [
                _h(1, 5, 47900),
                _h(2, 5, 30000, store="danawa", edition="physical", platform="PS5", cond="used"),
                _h(3, 4, 60000, store="danawa", edition="physical", platform="PS5", cond="new"),
            ]
        )
    body = client.get("/api/games/119133/history?platform=PS5&item_condition=used").json()
    assert (body["items"][0]["platform"], body["items"][0]["item_condition"]) == ("PS5", "used")
    assert body["platform"] == "PS5" and body["item_condition"] == "used"
    assert [i["price_krw"] for i in body["items"]] == [30000]
    both = client.get("/api/games/119133/history?platform=PS5").json()
    assert [i["price_krw"] for i in both["items"]] == [30000, 60000]
    assert [i["item_condition"] for i in both["items"]] == ["used", "new"]  # 항목마다 구분 가능
    mixed = client.get("/api/games/119133/history").json()["items"]  # 필터 없이도 플랫폼 구분
    assert {(i["platform"], i["item_condition"]) for i in mixed} == {
        ("PC", "new"),
        ("PS5", "used"),
        ("PS5", "new"),
    }


def test_history_dedup_keeps_latest_row(env) -> None:
    client, engine, _ = env
    with seed(engine) as s:
        s.add_all(
            [
                _h(1, 3, 47900),
                _h(2, 3, 45000),  # 같은 키·같은 시각 → 나중에 들어온(id 큰) 행만
                _h(3, 3, 52000, edition="physical"),  # edition이 다르면 별개
                _h(4, 3, 47000, store="epic"),  # store가 다르면 별개
            ]
        )
    items = client.get("/api/games/119133/history").json()["items"]
    assert sorted((i["store"], i["edition"], i["price_krw"]) for i in items) == [
        ("epic", "digital", 47000),
        ("steam", "digital", 45000),
        ("steam", "physical", 52000),
    ]


def test_dedupe_unit() -> None:
    rows = [_h(5, 1, 100), _h(9, 1, 200), _h(7, 1, 150, platform="PS5")]
    kept = dedupe(rows)
    assert sorted(r.id for r in kept) == [7, 9]


def test_history_empty_and_errors(env) -> None:
    client, *_ = env
    assert client.get("/api/games/5/history").json()["items"] == []
    r = client.get("/api/games/999/history")
    assert r.status_code == 404 and r.json()["error"]["code"] == "NOT_FOUND"
    for q in ("days=0", "days=abc", "item_condition=broken", "days=99999"):
        bad = client.get(f"/api/games/5/history?{q}")
        assert bad.status_code == 422 and bad.json()["error"]["code"] == "INVALID_REQUEST", q
