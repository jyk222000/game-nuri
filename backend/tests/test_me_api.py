"""찜(#17)·목표가 알림(#19 POST·PATCH)·메일 수신 설정(#22) API. 실제 DB 없이 SQLite로 검증한다."""

from datetime import datetime

import pytest
from app.api.deps import CurrentUser, get_current_user
from app.db.base import Base
from app.db.models import Alert, NotificationSetting, User, Wishlist
from app.db.session import get_write_db
from app.main import app
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

NOW = datetime(2026, 11, 23)


@pytest.fixture
def env():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        s.add_all(
            [
                User(user_id=1, email="a@example.com", created_at=NOW),
                User(user_id=2, email="b@example.com", created_at=NOW),
            ]
        )
        s.commit()

    def db():
        with Session(engine) as s:
            yield s

    current = {"id": 1}
    app.dependency_overrides[get_write_db] = db
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(user_id=current["id"])
    yield TestClient(app), engine, current
    app.dependency_overrides.clear()


def rows(engine, model):
    with Session(engine) as s:
        return s.scalars(select(model)).all()


# ---------- #17 찜 ----------
def test_wish_add_is_idempotent(env) -> None:
    client, engine, _ = env
    for _ in range(2):
        r = client.post("/api/me/wishlist", json={"game_id": 119133})
        assert r.status_code == 200
        assert r.json() == {"game_id": 119133, "wished": True}
    assert len(rows(engine, Wishlist)) == 1


def test_wish_delete_is_idempotent(env) -> None:
    client, engine, _ = env
    client.post("/api/me/wishlist", json={"game_id": 5})
    for _ in range(2):
        r = client.delete("/api/me/wishlist", params={"game_id": 5})
        assert r.status_code == 200
        assert r.json() == {"game_id": 5, "wished": False}
    assert rows(engine, Wishlist) == []


def test_wish_is_per_user(env) -> None:
    client, engine, current = env
    client.post("/api/me/wishlist", json={"game_id": 5})
    current["id"] = 2
    client.delete("/api/me/wishlist", params={"game_id": 5})  # 남의 찜은 지워지지 않는다
    assert len(rows(engine, Wishlist)) == 1


@pytest.mark.parametrize("body", [{}, {"game_id": "x"}, {"game_id": 0}, {"game_id": -3}])
def test_wish_invalid_body_is_422(env, body) -> None:
    client, *_ = env
    r = client.post("/api/me/wishlist", json=body)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "INVALID_REQUEST"


def test_wish_delete_requires_game_id(env) -> None:
    client, *_ = env
    r = client.delete("/api/me/wishlist")
    assert r.status_code == 422 and r.json()["error"]["code"] == "INVALID_REQUEST"


# ---------- #19 알림 POST·PATCH ----------
def test_alert_create_and_overwrite(env) -> None:
    client, engine, _ = env
    first = client.post("/api/me/alerts", json={"game_id": 7, "target_price_krw": 40000})
    assert first.status_code == 200
    body = first.json()
    assert body["target_price_krw"] == 40000 and body["active"] is True
    assert body["created_at"].endswith("Z")

    # 같은 (user, game)이면 409가 아니라 덮어쓴다 (행은 1개, 만든 시각 유지, 다시 켜짐)
    client.patch(f"/api/me/alerts/{body['alert_id']}", json={"active": False})
    second = client.post("/api/me/alerts", json={"game_id": 7, "target_price_krw": 30000})
    assert second.status_code == 200
    assert second.json()["alert_id"] == body["alert_id"]
    assert second.json()["target_price_krw"] == 30000 and second.json()["active"] is True
    assert second.json()["created_at"] == body["created_at"]
    assert len(rows(engine, Alert)) == 1


@pytest.mark.parametrize("price", [0, -1, 2_147_483_648])
def test_alert_invalid_price_is_400(env, price) -> None:
    client, *_ = env
    r = client.post("/api/me/alerts", json={"game_id": 7, "target_price_krw": price})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "INVALID_PRICE"


def test_alert_wrong_type_is_422(env) -> None:
    client, *_ = env
    r = client.post("/api/me/alerts", json={"game_id": 7, "target_price_krw": "abc"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "INVALID_REQUEST"


def test_alert_patch(env) -> None:
    client, *_ = env
    a = client.post("/api/me/alerts", json={"game_id": 7, "target_price_krw": 40000}).json()
    r = client.patch(f"/api/me/alerts/{a['alert_id']}", json={"target_price_krw": 35000})
    assert r.status_code == 200 and r.json()["target_price_krw"] == 35000
    r = client.patch(f"/api/me/alerts/{a['alert_id']}", json={"active": False})
    assert r.json()["active"] is False and r.json()["target_price_krw"] == 35000


def test_alert_patch_invalid(env) -> None:
    client, *_ = env
    a = client.post("/api/me/alerts", json={"game_id": 7, "target_price_krw": 40000}).json()
    assert client.patch(f"/api/me/alerts/{a['alert_id']}", json={}).status_code == 422
    r = client.patch(f"/api/me/alerts/{a['alert_id']}", json={"target_price_krw": 0})
    assert r.status_code == 400 and r.json()["error"]["code"] == "INVALID_PRICE"


def test_alert_patch_not_found_or_others(env) -> None:
    client, _, current = env
    a = client.post("/api/me/alerts", json={"game_id": 7, "target_price_krw": 40000}).json()
    current["id"] = 2
    for alert_id in (a["alert_id"], 99999):  # 남의 것과 없는 것이 똑같이 보인다
        r = client.patch(f"/api/me/alerts/{alert_id}", json={"active": False})
        assert r.status_code == 404 and r.json()["error"]["code"] == "NOT_FOUND"


def test_alert_delete_not_implemented_yet(env) -> None:
    client, *_ = env
    assert client.delete("/api/me/alerts/1").status_code in (404, 405)


# ---------- #22 메일 수신 설정 ----------
def test_notifications_default_true_without_row(env) -> None:
    client, engine, _ = env
    r = client.get("/api/me/notifications")
    assert r.status_code == 200 and r.json() == {"email_enabled": True}
    assert rows(engine, NotificationSetting) == []  # GET은 행을 만들지 않는다


def test_notifications_put_upserts(env) -> None:
    client, engine, _ = env
    assert client.put("/api/me/notifications", json={"email_enabled": False}).json() == {
        "email_enabled": False
    }
    assert client.get("/api/me/notifications").json() == {"email_enabled": False}
    client.put("/api/me/notifications", json={"email_enabled": True})
    assert client.get("/api/me/notifications").json() == {"email_enabled": True}
    assert len(rows(engine, NotificationSetting)) == 1


def test_notifications_put_validation(env) -> None:
    client, *_ = env
    assert client.put("/api/me/notifications", json={}).status_code == 422
    r = client.put("/api/me/notifications", json={"email_enabled": "maybe"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "INVALID_REQUEST"


# ---------- 로그인 ----------
@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("post", "/api/me/wishlist", {"game_id": 1}),
        ("delete", "/api/me/wishlist?game_id=1", None),
        ("post", "/api/me/alerts", {"game_id": 1, "target_price_krw": 100}),
        ("patch", "/api/me/alerts/1", {"active": True}),
        ("get", "/api/me/notifications", None),
        ("put", "/api/me/notifications", {"email_enabled": True}),
    ],
)
def test_login_required(method, path, body) -> None:
    app.dependency_overrides.clear()  # 가짜 사용자 꺼짐(기본)이라 세션 없이는 401
    r = getattr(TestClient(app), method)(path, **({"json": body} if body is not None else {}))
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "UNAUTHORIZED"
