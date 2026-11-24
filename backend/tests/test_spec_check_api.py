"""GET /api/games/{id}/spec-check 라우터 연결(#31). AI·Valkey는 가짜, DB는 SQLite 메모리.

판정 로직·프롬프트는 test_spec_check_service.py가 확인한다. 여기서는 라우터가 로그인한 사용자의
사양을 쓰는지, 오류가 계약대로 나가는지, 캐시가 요청 사이에 유지되는지를 본다.
"""

import json as jsonlib

import httpx
import pytest
from app.core import config
from app.db.models import GameRequirement, UserSpec
from app.main import app
from app.services import spec_check
from fastapi.testclient import TestClient

from tests.conftest import NOW, seed

KEY = "test-key-not-real"
ANSWER = {"verdict": "min_ok", "reason": "GPU가 권장보다 낮아요"}


class FakeAi:
    def __init__(self, error: Exception | None = None) -> None:
        self.calls: list[dict] = []
        self.error = error

    def __call__(self, url, json=None, headers=None, timeout=None):  # noqa: ANN001, ANN204
        self.calls.append({"url": url, "json": json, "headers": headers})
        if self.error:
            raise self.error
        text = jsonlib.dumps(ANSWER, ensure_ascii=False)
        body = {"candidates": [{"content": {"parts": [{"text": text}]}}]}
        return httpx.Response(200, json=body, request=httpx.Request("POST", url))


class FakeValkey:
    def __init__(self) -> None:
        self.data: dict[str, str] = {}

    def get(self, key):  # noqa: ANN001
        return self.data.get(key)

    def set(self, key, value, ex=None):  # noqa: ANN001
        self.data[key] = value


def _configure(monkeypatch, **over) -> None:  # noqa: ANN001, ANN003
    values = dict(gemini_api_key=KEY, ai_model="test-model")
    values.update(over)
    monkeypatch.setattr(
        spec_check, "get_backend_settings", lambda: config.BackendSettings(_env_file=None, **values)
    )


@pytest.fixture
def ai(env, monkeypatch):  # noqa: ANN001
    """(client, current, fake_ai, valkey). 게임 7에는 사양이, 사용자 1에는 내 PC 사양이 있다."""
    client, engine, current = env
    with seed(engine) as s:
        s.add_all(
            [
                GameRequirement(
                    game_id=7,
                    minimum_text="CPU: i5-4460 / GPU: GTX 960",
                    recommended_text="CPU: i7-8700 / GPU: GTX 1060",
                    updated_at=NOW,
                ),
                UserSpec(user_id=1, cpu="i7-12700", gpu="GTX 1050", ram_gb=16, updated_at=NOW),
            ]
        )
    fake, valkey = FakeAi(), FakeValkey()
    monkeypatch.setattr(spec_check.httpx, "post", fake)
    monkeypatch.setattr(spec_check, "get_valkey", lambda: valkey)
    _configure(monkeypatch)
    return client, current, fake, valkey


def test_spec_check_returns_contract_shape_and_caches(ai) -> None:  # noqa: ANN001
    client, _, fake, _ = ai
    first = client.get("/api/games/7/spec-check")
    assert first.status_code == 200
    assert first.json() == {
        "game_id": 7,
        "verdict": "min_ok",
        "reason": "GPU가 권장보다 낮아요",
        "generated_by": "ai",
        "cached": False,
    }
    second = client.get("/api/games/7/spec-check").json()
    assert second["cached"] is True and second["verdict"] == "min_ok"
    assert len(fake.calls) == 1  # 두 번째 요청은 AI를 부르지 않는다


def test_spec_check_uses_the_logged_in_users_specs(ai) -> None:  # noqa: ANN001
    client, current, fake, _ = ai
    client.get("/api/games/7/spec-check")
    prompt = fake.calls[0]["json"]["contents"][0]["parts"][0]["text"]
    assert "GTX 1050" in prompt and "i7-12700" in prompt  # 사용자 1의 사양
    current["id"] = 2  # 사양을 입력하지 않은 다른 사용자
    r = client.get("/api/games/7/spec-check")
    assert r.status_code == 400 and r.json()["error"]["code"] == "SPEC_REQUIRED"
    assert len(fake.calls) == 1  # 사양이 없는 사용자에게는 AI를 부르지 않는다


def test_spec_check_does_not_send_user_identity_or_leak_key(ai) -> None:  # noqa: ANN001
    client, _, fake, _ = ai
    response = client.get("/api/games/7/spec-check")
    sent = jsonlib.dumps(fake.calls[0]["json"], ensure_ascii=False)
    assert "a@example.com" not in sent  # 사용자 식별 정보는 보내지 않는다
    assert KEY not in response.text and KEY not in sent  # 키는 본문·응답에 없다 (헤더로만)
    assert fake.calls[0]["headers"]["x-goog-api-key"] == KEY


def test_game_without_requirements_is_404(ai) -> None:  # noqa: ANN001
    client, _, fake, _ = ai
    r = client.get("/api/games/5/spec-check")  # 게임 5에는 사양 행이 없다
    assert r.status_code == 404 and r.json()["error"]["code"] == "NOT_FOUND"
    assert fake.calls == []


def test_unknown_game_is_404(ai) -> None:  # noqa: ANN001
    client, *_ = ai
    r = client.get("/api/games/999999/spec-check")
    assert r.status_code == 404 and r.json()["error"]["code"] == "NOT_FOUND"


def test_ai_failure_is_503_and_not_cached(env, monkeypatch) -> None:  # noqa: ANN001
    client, engine, _ = env
    with seed(engine) as s:
        s.add_all(
            [
                GameRequirement(
                    game_id=7, minimum_text="CPU: i5", recommended_text="CPU: i7", updated_at=NOW
                ),
                UserSpec(user_id=1, cpu="i7-12700", gpu="GTX 1050", ram_gb=16, updated_at=NOW),
            ]
        )
    fake, valkey = FakeAi(error=httpx.ConnectError("down")), FakeValkey()
    monkeypatch.setattr(spec_check.httpx, "post", fake)
    monkeypatch.setattr(spec_check, "get_valkey", lambda: valkey)
    _configure(monkeypatch)
    for _ in range(2):
        r = client.get("/api/games/7/spec-check")
        assert r.status_code == 503 and r.json()["error"]["code"] == "UNAVAILABLE"
    assert len(fake.calls) == 2 and valkey.data == {}  # 실패는 저장하지 않아 다시 시도한다


@pytest.mark.parametrize("missing", [{"gemini_api_key": ""}, {"ai_model": ""}])
def test_missing_ai_settings_is_503_without_calling_ai(ai, monkeypatch, missing) -> None:  # noqa: ANN001
    client, _, fake, _ = ai
    _configure(monkeypatch, **missing)
    r = client.get("/api/games/7/spec-check")
    assert r.status_code == 503 and r.json()["error"]["code"] == "UNAVAILABLE"
    assert fake.calls == []


def test_spec_check_requires_login() -> None:
    app.dependency_overrides.clear()  # 가짜 사용자 꺼짐(기본)이라 세션 없이는 401
    r = TestClient(app).get("/api/games/7/spec-check")
    assert r.status_code == 401 and r.json()["error"]["code"] == "UNAUTHORIZED"
