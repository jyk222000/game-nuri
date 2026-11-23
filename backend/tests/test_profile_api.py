"""#3 내 정보, #4 Steam ID 연동, #30 내 PC 사양 등록·조회."""

import pytest
from app.main import app
from fastapi.testclient import TestClient


# ---------- #3 ----------
def test_get_me(env) -> None:
    client, *_ = env
    assert client.get("/api/me").json() == {
        "user_id": 1,
        "email": "a@example.com",
        "name": None,
        "steam_id": None,
    }


def test_patch_me_sets_nickname_and_no_picture(env) -> None:
    client, *_ = env
    r = client.patch("/api/me", json={"name": "  겜누리 사용자 "})
    assert r.status_code == 200
    assert r.json()["name"] == "겜누리 사용자"
    assert "picture" not in r.json()
    assert client.get("/api/me").json()["name"] == "겜누리 사용자"


@pytest.mark.parametrize(
    "body", [{}, {"name": ""}, {"name": "   "}, {"name": "x" * 65}, {"name": 1}]
)
def test_patch_me_validation(env, body) -> None:
    client, *_ = env
    r = client.patch("/api/me", json=body)
    assert r.status_code == 422 and r.json()["error"]["code"] == "INVALID_REQUEST"


def test_me_isolated_per_user(env) -> None:
    client, _, current = env
    client.patch("/api/me", json={"name": "A"})
    current["id"] = 2
    assert client.get("/api/me").json()["name"] is None


def test_me_unknown_user_404(env) -> None:
    client, _, current = env
    current["id"] = 999
    r = client.get("/api/me")
    assert r.status_code == 404 and r.json()["error"]["code"] == "NOT_FOUND"


# ---------- #4 ----------
def test_put_steam(env) -> None:
    client, *_ = env
    r = client.put("/api/me/steam", json={"steam_id": "76561198000000000"})
    assert r.status_code == 200 and r.json() == {"steam_id": "76561198000000000"}
    assert client.get("/api/me").json()["steam_id"] == "76561198000000000"


@pytest.mark.parametrize(
    "value", ["", "1234", "7656119800000000", "765611980000000000", "7656119800000000a"]
)
def test_put_steam_invalid_is_400(env, value) -> None:
    client, *_ = env
    r = client.put("/api/me/steam", json={"steam_id": value})
    assert r.status_code == 400 and r.json()["error"]["code"] == "INVALID_STEAM_ID"
    assert client.get("/api/me").json()["steam_id"] is None


def test_put_steam_wrong_type_is_422(env) -> None:
    client, *_ = env
    r = client.put("/api/me/steam", json={"steam_id": 76561198000000000})
    assert r.status_code == 422 and r.json()["error"]["code"] == "INVALID_REQUEST"


# ---------- #30 ----------
def test_specs_empty_default(env) -> None:
    client, *_ = env
    assert client.get("/api/me/specs").json() == {"cpu": "", "gpu": "", "ram_gb": None, "os": ""}


def test_specs_put_then_get_and_replace(env) -> None:
    client, *_ = env
    body = {"cpu": "Ryzen 5 5600", "gpu": "RTX 3060", "ram_gb": 16, "os": "Windows 11"}
    assert client.put("/api/me/specs", json=body).json() == body
    assert client.get("/api/me/specs").json() == body
    # PUT은 통째로 바꾼다: 빠진 항목은 미입력이 된다
    assert client.put("/api/me/specs", json={"gpu": "RTX 4070"}).json() == {
        "cpu": "",
        "gpu": "RTX 4070",
        "ram_gb": None,
        "os": "",
    }


def test_specs_isolated_per_user(env) -> None:
    client, _, current = env
    client.put("/api/me/specs", json={"cpu": "A"})
    current["id"] = 2
    assert client.get("/api/me/specs").json()["cpu"] == ""


@pytest.mark.parametrize(
    "body", [{"ram_gb": 0}, {"ram_gb": "많이"}, {"cpu": "x" * 129}, {"os": "x" * 65}]
)
def test_specs_validation(env, body) -> None:
    client, *_ = env
    r = client.put("/api/me/specs", json=body)
    assert r.status_code == 422 and r.json()["error"]["code"] == "INVALID_REQUEST"


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/api/me"),
        ("patch", "/api/me"),
        ("put", "/api/me/steam"),
        ("get", "/api/me/specs"),
        ("put", "/api/me/specs"),
    ],
)
def test_profile_requires_login(method, path) -> None:
    app.dependency_overrides.clear()
    r = getattr(TestClient(app), method)(path, **({"json": {}} if method != "get" else {}))
    assert r.status_code == 401 and r.json()["error"]["code"] == "UNAUTHORIZED"
