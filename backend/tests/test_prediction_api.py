"""#16 할인 예측: 최근 2년 할인 주기. 이력 부족이면 confidence = insufficient_data."""

from datetime import UTC, datetime, timedelta

import pytest
from app.db.models import PriceHistory

from tests.conftest import seed

NOW = datetime.now(UTC).replace(tzinfo=None, microsecond=0)
_ids = iter(range(1, 10_000))


def _h(days_ago, price, pct, platform="PC", cond="new", store="steam"):
    return PriceHistory(
        id=next(_ids),
        game_id=119133,
        store=store,
        edition="digital",
        platform=platform,
        item_condition=cond,
        price_krw=price,
        regular_krw=64800,
        discount_pct=pct,
        collected_at=NOW - timedelta(days=days_ago),
    )


def _sales(*events):
    """(며칠 전, 할인율) 마다 할인 하루 + 바로 다음 날 정가 하루."""
    rows = []
    for days_ago, pct in events:
        rows += [_h(days_ago, 40000, pct), _h(days_ago - 1, 64800, 0)]
    return rows


def _pred(client):
    r = client.get("/api/games/119133/prediction")
    assert r.status_code == 200
    return r.json()


def test_prediction_interval_next_date_and_discount(env) -> None:
    client, engine, _ = env
    with seed(engine) as s:
        s.add_all(_sales((90, 40), (30, 50)))
    body = _pred(client)
    assert body == {
        "game_id": 119133,
        "avg_sale_interval_days": 60,
        "next_sale_expected": (NOW - timedelta(days=30) + timedelta(days=60)).date().isoformat(),
        "expected_discount_pct": 45,
        "confidence": "low",
        "basis": "최근 2년 할인 2회 기준",
    }


def test_prediction_past_expected_date_falls_back_to_two_weeks(env) -> None:
    client, engine, _ = env
    with seed(engine) as s:
        s.add_all(_sales((300, 40), (240, 40)))  # 예상일(180일 전)이 이미 지났다
    body = _pred(client)
    assert body["avg_sale_interval_days"] == 60
    assert body["next_sale_expected"] == (NOW + timedelta(days=14)).date().isoformat()


@pytest.mark.parametrize(("count", "confidence"), [(2, "low"), (4, "medium"), (8, "high")])
def test_prediction_confidence_by_sale_count(env, count, confidence) -> None:
    client, engine, _ = env
    with seed(engine) as s:
        s.add_all(_sales(*[(30 * i + 10, 40) for i in range(count)]))
    body = _pred(client)
    assert body["confidence"] == confidence
    assert body["basis"] == f"최근 2년 할인 {count}회 기준"


def test_prediction_ignores_sales_older_than_2_years(env) -> None:
    client, engine, _ = env
    with seed(engine) as s:
        s.add_all(_sales((900, 40), (800, 40), (30, 30)))  # 2년 안은 1회뿐
    assert _pred(client)["confidence"] == "insufficient_data"


def test_prediction_insufficient_cases(env) -> None:
    client, engine, _ = env
    expected_null = {
        "avg_sale_interval_days": None,
        "next_sale_expected": None,
        "expected_discount_pct": None,
        "confidence": "insufficient_data",
    }
    # 이력 없음
    body = _pred(client)
    assert {k: body[k] for k in expected_null} == expected_null
    # 할인 1회뿐
    with seed(engine) as s:
        s.add_all(_sales((30, 40)))
    body = _pred(client)
    assert {k: body[k] for k in expected_null} == expected_null
    assert body["basis"]  # 이유 문장이 있다


def test_prediction_console_only_is_insufficient(env) -> None:
    client, engine, _ = env
    with seed(engine) as s:
        s.add_all([_h(d, 30000, 40, platform="PS5", store="danawa") for d in (5, 30, 60, 90)])
    assert _pred(client)["confidence"] == "insufficient_data"


def test_prediction_404_and_422(env) -> None:
    client, *_ = env
    r = client.get("/api/games/999/prediction")
    assert r.status_code == 404 and r.json()["error"]["code"] == "NOT_FOUND"
    r = client.get("/api/games/abc/prediction")
    assert r.status_code == 422 and r.json()["error"]["code"] == "INVALID_REQUEST"
