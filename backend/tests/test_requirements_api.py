"""#29 게임 최소·권장 사양: game_requirements 텍스트 그대로."""

from datetime import datetime

from app.db.models import GameRequirement

from tests.conftest import seed


def test_requirements_text_as_is(env) -> None:
    client, engine, _ = env
    with seed(engine) as s:
        s.add(
            GameRequirement(
                game_id=119133,
                minimum_text="OS: Windows 10 ... 그래픽: GTX 1060 ...",
                recommended_text="OS: Windows 10/11 ...",
                updated_at=datetime(2026, 11, 19, 2, 30),
            )
        )
    assert client.get("/api/games/119133/requirements").json() == {
        "game_id": 119133,
        "minimum_text": "OS: Windows 10 ... 그래픽: GTX 1060 ...",
        "recommended_text": "OS: Windows 10/11 ...",
        "updated_at": "2026-11-19T02:30:00Z",
    }


def test_requirements_missing_row_is_nulls(env) -> None:
    client, *_ = env
    assert client.get("/api/games/5/requirements").json() == {
        "game_id": 5,
        "minimum_text": None,
        "recommended_text": None,
        "updated_at": None,
    }


def test_requirements_partial_text(env) -> None:
    client, engine, _ = env
    with seed(engine) as s:
        s.add(
            GameRequirement(
                game_id=7,
                minimum_text="최소만",
                recommended_text=None,
                updated_at=datetime(2026, 1, 1),
            )
        )
    body = client.get("/api/games/7/requirements").json()
    assert body["minimum_text"] == "최소만" and body["recommended_text"] is None


def test_requirements_404_and_422(env) -> None:
    client, *_ = env
    r = client.get("/api/games/999/requirements")
    assert r.status_code == 404 and r.json()["error"]["code"] == "NOT_FOUND"
    r = client.get("/api/games/abc/requirements")
    assert r.status_code == 422 and r.json()["error"]["code"] == "INVALID_REQUEST"
