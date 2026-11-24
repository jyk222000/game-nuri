"""#15 구매 타이밍: buy_now / neutral / wait / insufficient_data (임시 규칙, services/timing.py)."""

from datetime import UTC, datetime, timedelta

import pytest
from app.db.models import PriceHistory
from app.services.timing import Day, sale_events

from tests.conftest import seed

NOW = datetime.now(UTC).replace(tzinfo=None, microsecond=0)
_ids = iter(range(1, 10_000))


def _h(days_ago, price, pct, platform="PC", cond="new", store="steam", game_id=119133):
    return PriceHistory(
        id=next(_ids),
        game_id=game_id,
        store=store,
        edition="digital",
        platform=platform,
        item_condition=cond,
        price_krw=price,
        regular_krw=64800,
        discount_pct=pct,
        collected_at=NOW - timedelta(days=days_ago),
    )


def _timing(client, game_id=119133):
    r = client.get(f"/api/games/{game_id}/timing")
    assert r.status_code == 200
    return r.json()


def test_buy_now_near_lowest_and_discounted(env) -> None:
    client, engine, _ = env
    with seed(engine) as s:
        s.add_all([_h(100, 64800, 0), _h(60, 40000, 38), _h(1, 41200, 36)])
    body = _timing(client)
    assert body["verdict"] == "buy_now"
    assert body["current_krw"] == 41200 and body["lowest_krw"] == 40000
    assert body["lowest_date"] == (NOW - timedelta(days=60)).date().isoformat()
    assert body["vs_lowest_pct"] == 3 and body["sale_count_2y"] == 1
    assert set(body) == {
        "game_id",
        "verdict",
        "reason",
        "current_krw",
        "lowest_krw",
        "lowest_date",
        "vs_lowest_pct",
        "sale_count_2y",
    }


def test_neutral_discounted_but_far_from_lowest(env) -> None:
    client, engine, _ = env
    with seed(engine) as s:
        s.add_all([_h(100, 64800, 0), _h(60, 40000, 38), _h(1, 50000, 20)])
    body = _timing(client)
    assert body["verdict"] == "neutral" and body["vs_lowest_pct"] == 25
    assert "40,000원" in body["reason"]


def test_high_discount_but_not_near_lowest_is_neutral(env) -> None:
    client, engine, _ = env
    with seed(engine) as s:
        s.add_all([_h(100, 64800, 0), _h(60, 20000, 70), _h(1, 45000, 31)])
    assert _timing(client)["verdict"] == "neutral"


def test_wait_without_prediction(env) -> None:
    client, engine, _ = env
    with seed(engine) as s:
        s.add_all([_h(100, 64800, 0), _h(60, 40000, 38), _h(1, 64800, 0)])
    body = _timing(client)
    assert body["verdict"] == "wait" and body["vs_lowest_pct"] == 62
    assert body["reason"] == "정가에 가까워요."  # 할인 1회뿐이라 다음 할인 예상일은 없다


def test_wait_with_next_sale_date(env) -> None:
    client, engine, _ = env
    with seed(engine) as s:
        s.add_all(
            [_h(150, 64800, 0), _h(90, 40000, 40), _h(60, 64800, 0), _h(30, 40000, 40)]
            + [_h(1, 64800, 0)]
        )
    body = _timing(client)
    expected = (NOW - timedelta(days=30) + timedelta(days=60)).date().isoformat()
    assert body["verdict"] == "wait" and body["sale_count_2y"] == 2
    assert body["reason"] == f"정가에 가까워요. 다음 할인은 {expected} 전후로 예상돼요."


def test_insufficient_when_fewer_than_3_days(env) -> None:
    client, engine, _ = env
    with seed(engine) as s:
        s.add_all([_h(10, 50000, 20), _h(1, 47900, 26)])
    assert _timing(client) == {
        "game_id": 119133,
        "verdict": "insufficient_data",
        "reason": "가격 이력이 부족해 아직 판단하기 어려워요.",
        "current_krw": None,
        "lowest_krw": None,
        "lowest_date": None,
        "vs_lowest_pct": None,
        "sale_count_2y": None,
    }


def test_insufficient_when_no_history_at_all(env) -> None:
    client, *_ = env
    assert _timing(client, 5)["verdict"] == "insufficient_data"


def test_console_only_is_insufficient_even_with_many_rows(env) -> None:
    client, engine, _ = env
    with seed(engine) as s:
        s.add_all([_h(d, 50000, 0, platform="PS5", store="danawa") for d in range(1, 8)])
    body = _timing(client)
    assert body["verdict"] == "insufficient_data" and "콘솔" in body["reason"]


def test_used_and_console_rows_do_not_affect_pc_timing(env) -> None:
    client, engine, _ = env
    with seed(engine) as s:
        s.add_all(
            [_h(100, 64800, 0), _h(60, 40000, 38), _h(1, 41200, 36)]
            + [_h(2, 1000, 90, platform="PS5", store="danawa"), _h(3, 500, 90, cond="used")]
        )
    body = _timing(client)
    assert body["lowest_krw"] == 40000 and body["verdict"] == "buy_now"


def test_same_day_uses_cheapest_store(env) -> None:
    client, engine, _ = env
    with seed(engine) as s:
        s.add_all(
            [_h(100, 64800, 0), _h(60, 40000, 38), _h(1, 41200, 36), _h(1, 60000, 5, store="epic")]
        )
    assert _timing(client)["current_krw"] == 41200


def test_timing_404_and_422(env) -> None:
    client, *_ = env
    r = client.get("/api/games/999/timing")
    assert r.status_code == 404 and r.json()["error"]["code"] == "NOT_FOUND"
    r = client.get("/api/games/abc/timing")
    assert r.status_code == 422 and r.json()["error"]["code"] == "INVALID_REQUEST"


@pytest.mark.parametrize(
    ("pcts", "count"),
    [([0, 0], 0), ([10, 0, 30], 2), ([10, 20, 30], 1), ([9, 9, 9], 0), ([0, 10, 10, 0, 10], 2)],
)
def test_sale_events_grouping(pcts, count) -> None:
    base = datetime(2026, 1, 1).date()
    days = [Day(base + timedelta(days=i), 1000, p) for i, p in enumerate(pcts)]
    assert len(sale_events(days)) == count


# ---------- 무료 게임: 최저가 0원이어도 500이 아니다 ----------


def test_free_game_all_zero_history_is_200_buy_now(env) -> None:
    client, engine, _ = env
    with seed(engine) as s:
        s.add_all([_h(d, 0, 0) for d in (40, 30, 20, 10, 1)])
    body = _timing(client)
    assert body["verdict"] == "buy_now" and "무료" in body["reason"]
    assert body["current_krw"] == 0 and body["lowest_krw"] == 0
    assert body["vs_lowest_pct"] == 0 and body["sale_count_2y"] == 0


def test_was_free_but_paid_now_has_no_percent(env) -> None:
    client, engine, _ = env
    with seed(engine) as s:
        s.add_all([_h(30, 0, 100), _h(20, 0, 100), _h(1, 20000, 0)])
    body = _timing(client)
    assert body["lowest_krw"] == 0 and body["current_krw"] == 20000
    assert body["vs_lowest_pct"] is None  # 0원 대비 비율은 정의되지 않는다
    assert body["verdict"] == "wait"


# ---------- 마지막 날에 일부 스토어 행만 있어도 현재가는 모든 스토어 기준 ----------


def test_current_uses_last_price_of_every_store(env) -> None:
    """msstore 할인(19,770)은 어제 행, 오늘은 gog 행뿐. 그래도 현재가는 19,770이다."""
    client, engine, _ = env
    with seed(engine) as s:
        s.add_all(
            [
                _h(100, 80632, 0, store="gog"),
                _h(100, 66000, 0, store="msstore"),
                _h(2, 19770, 70, store="msstore"),
                _h(1, 80632, 0, store="gog"),  # 마지막 날은 gog 행만
            ]
        )
    body = _timing(client)
    assert body["current_krw"] == 19770 and body["lowest_krw"] == 19770
    assert body["verdict"] == "buy_now" and body["vs_lowest_pct"] == 0


def test_price_rise_in_one_store_does_not_hide_other_store_sale(env) -> None:
    """같은 날 다른 스토어 가격이 올라도, 그 스토어의 이전 가격이 남아 있으면 안 된다."""
    client, engine, _ = env
    with seed(engine) as s:
        s.add_all(
            [
                _h(10, 30000, 40, store="gog"),
                _h(5, 50000, 0, store="msstore"),
                _h(1, 64800, 0, store="gog"),  # gog 할인 종료 → 최저는 msstore 50,000
            ]
        )
    assert _timing(client)["current_krw"] == 50000


def test_sale_is_not_split_by_other_stores_rows(env) -> None:
    """할인 중인 스토어의 행이 없는 날(다른 스토어 행만 있는 날)에도 할인 구간은 이어진다."""
    client, engine, _ = env
    with seed(engine) as s:
        s.add_all(
            [
                _h(40, 80000, 0, store="gog"),
                _h(40, 80000, 0, store="msstore"),
                _h(30, 20000, 75, store="msstore"),  # 할인 시작
                _h(20, 80000, 0, store="gog"),  # 그 사이 gog 행만
                _h(10, 20000, 75, store="msstore"),  # 같은 할인 재수집
            ]
        )
    assert _timing(client)["sale_count_2y"] == 1


def test_same_store_same_day_uses_last_collected_row(env) -> None:
    client, engine, _ = env
    with seed(engine) as s:
        s.add_all([_h(100, 64800, 0), _h(60, 40000, 38), _h(1, 50000, 20), _h(1, 41200, 36)])
    # 같은 날 같은 스토어: 더 늦게 수집된 행(id가 큰 쪽)이 그날 가격
    assert _timing(client)["current_krw"] == 41200
