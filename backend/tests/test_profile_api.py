"""#3 내 정보, #4 Steam ID 연동, #30 내 PC 사양 등록·조회."""

from datetime import datetime

import httpx
import pytest
from app.clients import steam
from app.db.models import UserOwnedGame
from app.main import app
from fastapi.testclient import TestClient
from gamenuri_common.config import get_settings
from sqlalchemy import select
from sqlalchemy.orm import Session


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
STEAM_ID = "76561198000000000"


def _owned(engine, user_id=1) -> dict[int, int]:
    with Session(engine) as s:
        rows = s.scalars(select(UserOwnedGame).where(UserOwnedGame.user_id == user_id))
        return {r.steam_appid: r.playtime_forever_min for r in rows}


def _fake_steam(monkeypatch, games=None, exc=None) -> list[str]:
    calls: list[str] = []

    def get_owned_games(steam_id):  # noqa: ANN001
        calls.append(steam_id)
        if exc:
            raise exc
        return games

    monkeypatch.setattr(steam, "get_owned_games", get_owned_games)
    return calls


def test_put_steam_saves_id_and_owned_games(env, monkeypatch) -> None:
    client, engine, _ = env
    calls = _fake_steam(monkeypatch, [steam.OwnedGame(500, 120), steam.OwnedGame(730, 0)])
    r = client.put("/api/me/steam", json={"steam_id": STEAM_ID})
    assert r.status_code == 200 and r.json() == {"steam_id": STEAM_ID, "owned_games": 2}
    assert calls == [STEAM_ID]
    assert client.get("/api/me").json()["steam_id"] == STEAM_ID
    assert _owned(engine) == {500: 120, 730: 0}  # appid와 플레이 시간(분)만 저장


def test_put_steam_again_replaces_owned_games_of_that_user_only(env, monkeypatch) -> None:
    client, engine, current = env
    _fake_steam(monkeypatch, [steam.OwnedGame(500, 120), steam.OwnedGame(730, 5)])
    client.put("/api/me/steam", json={"steam_id": STEAM_ID})
    current["id"] = 2
    client.put("/api/me/steam", json={"steam_id": "76561198000000001"})
    current["id"] = 1
    _fake_steam(monkeypatch, [steam.OwnedGame(500, 300)])  # 730은 사라지고 500은 갱신
    assert client.put("/api/me/steam", json={"steam_id": STEAM_ID}).json()["owned_games"] == 1
    assert _owned(engine, 1) == {500: 300}
    assert _owned(engine, 2) == {500: 120, 730: 5}


def test_put_steam_private_profile_is_400_and_saves_nothing(env, monkeypatch) -> None:
    client, engine, _ = env
    _fake_steam(monkeypatch, exc=steam.SteamPrivateProfile())
    r = client.put("/api/me/steam", json={"steam_id": STEAM_ID})
    assert r.status_code == 400 and r.json()["error"]["code"] == "STEAM_PROFILE_PRIVATE"
    assert "공개" in r.json()["error"]["message"]
    assert client.get("/api/me").json()["steam_id"] is None
    assert _owned(engine) == {}


def test_put_steam_unavailable_is_503_and_keeps_previous(env, monkeypatch) -> None:
    client, engine, _ = env
    _fake_steam(monkeypatch, [steam.OwnedGame(500, 1)])
    client.put("/api/me/steam", json={"steam_id": STEAM_ID})
    _fake_steam(monkeypatch, exc=steam.SteamUnavailable("ConnectError"))
    r = client.put("/api/me/steam", json={"steam_id": "76561198000000001"})
    assert r.status_code == 503 and r.json()["error"]["code"] == "UNAVAILABLE"
    assert client.get("/api/me").json()["steam_id"] == STEAM_ID
    assert _owned(engine) == {500: 1}


def test_put_steam_public_but_no_games_is_ok_with_zero(env, monkeypatch) -> None:
    client, engine, _ = env
    _fake_steam(monkeypatch, [])
    r = client.put("/api/me/steam", json={"steam_id": STEAM_ID})
    assert r.json() == {"steam_id": STEAM_ID, "owned_games": 0} and _owned(engine) == {}


# ---- Steam 클라이언트(키 보호, 응답 해석) ----
class _Resp:
    def __init__(self, payload, status=200) -> None:
        self.payload, self.status = payload, status

    def raise_for_status(self) -> None:
        if self.status >= 400:
            req = httpx.Request("GET", f"{steam.OWNED_GAMES_URL}?key=super-secret-key")
            raise httpx.HTTPStatusError("bad", request=req, response=httpx.Response(self.status))

    def json(self):
        return self.payload


@pytest.fixture
def steam_key(monkeypatch):
    monkeypatch.setenv("STEAM_KEY", "super-secret-key")
    get_settings.cache_clear()
    yield "super-secret-key"
    get_settings.cache_clear()


def test_steam_client_parses_games_and_sends_key_as_param(steam_key, monkeypatch) -> None:
    seen: dict = {}

    def fake_get(url, params=None, timeout=None):  # noqa: ANN001
        seen.update(url=url, params=params)
        payload = {
            "response": {
                "game_count": 2,
                "games": [
                    {"appid": 10, "playtime_forever": 5, "name": "ignored"},
                    {"appid": "x"},  # 모양이 다른 항목은 건너뜀
                    {"appid": 20},
                ],
            }
        }
        return _Resp(payload)

    monkeypatch.setattr(httpx, "get", fake_get)
    games = steam.get_owned_games(STEAM_ID)
    assert games == [steam.OwnedGame(10, 5), steam.OwnedGame(20, 0)]
    assert seen["url"] == steam.OWNED_GAMES_URL and seen["params"]["steamid"] == STEAM_ID
    assert "key" not in seen["url"]


def test_steam_client_empty_response_means_private(steam_key, monkeypatch) -> None:
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _Resp({"response": {}}))
    with pytest.raises(steam.SteamPrivateProfile):
        steam.get_owned_games(STEAM_ID)
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _Resp({"response": {"game_count": 0}}))
    assert steam.get_owned_games(STEAM_ID) == []


def test_steam_key_never_in_error_log_or_response(env, steam_key, monkeypatch, caplog) -> None:
    client, *_ = env
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _Resp({}, status=403))
    with caplog.at_level("DEBUG"):
        r = client.put("/api/me/steam", json={"steam_id": STEAM_ID})
    assert r.status_code == 503
    assert steam_key not in r.text and steam_key not in caplog.text
    assert STEAM_ID not in caplog.text


def test_steam_client_without_key_is_unavailable(monkeypatch) -> None:
    monkeypatch.setenv("STEAM_KEY", "")
    get_settings.cache_clear()
    try:
        with pytest.raises(steam.SteamUnavailable):
            steam.get_owned_games(STEAM_ID)
    finally:
        get_settings.cache_clear()


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


def test_steam_client_parses_last_played_time(steam_key, monkeypatch) -> None:
    payload = {
        "response": {
            "game_count": 4,
            "games": [
                {"appid": 1, "playtime_forever": 60, "rtime_last_played": 1795000000},
                {"appid": 2, "playtime_forever": 0, "rtime_last_played": 0},  # 0 = 플레이한 적 없음
                {"appid": 3, "rtime_last_played": "abc"},  # 이상한 값은 None
                {"appid": 4},  # 필드가 없으면 None
            ],
        }
    }
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _Resp(payload))
    games = {g.appid: g.rtime_last_played for g in steam.get_owned_games(STEAM_ID)}
    assert games == {1: datetime(2026, 11, 18, 11, 6, 40), 2: None, 3: None, 4: None}


def test_put_steam_stores_last_played_time(env, monkeypatch) -> None:
    client, engine, _ = env
    when = datetime(2026, 11, 20, 9, 30)
    _fake_steam(monkeypatch, [steam.OwnedGame(500, 120, when), steam.OwnedGame(730, 0)])
    assert client.put("/api/me/steam", json={"steam_id": STEAM_ID}).status_code == 200
    with Session(engine) as s:
        rows = {r.steam_appid: r.rtime_last_played for r in s.scalars(select(UserOwnedGame))}
    assert rows == {500: when, 730: None}
