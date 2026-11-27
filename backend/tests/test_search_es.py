"""#5 검색의 ES 스위치와 대체 경로. ES는 가짜로 확인한다(응답 모양은 실제 ES와 같게).

env 게임: 5 Five, 7 Seven, 119133 Elden Ring(엘든 링).
"""

import pytest
from app.core import config
from app.services import search
from elastic_transport import ConnectionError as EsConnectionError


class FakeEs:
    def __init__(self, ids: list | None = None, error: Exception | None = None, raw=None) -> None:  # noqa: ANN001
        self.ids, self.error, self.raw = ids or [], error, raw
        self.calls: list[dict] = []

    def search(self, **kwargs):  # noqa: ANN003, ANN201
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        if self.raw is not None:
            return self.raw
        return {"hits": {"hits": [{"_source": {"game_id": i}} for i in self.ids]}}


def use(monkeypatch, backend: str, es: FakeEs) -> FakeEs:  # noqa: ANN001
    s = config.BackendSettings(_env_file=None, search_backend=backend)
    monkeypatch.setattr(search, "get_backend_settings", lambda: s)
    monkeypatch.setattr(search, "get_es", lambda: es)
    return es


def ids(client, q: str) -> list[int]:  # noqa: ANN001
    r = client.get("/api/games", params={"q": q})
    assert r.status_code == 200
    return [c["game_id"] for c in r.json()["items"]]


def test_default_is_db_and_never_calls_es(env, monkeypatch) -> None:  # noqa: ANN001
    client, _, _ = env
    assert config.BackendSettings(_env_file=None).search_backend == "db"
    es = use(monkeypatch, "db", FakeEs(ids=[119133]))
    assert ids(client, "elden rnig") == []  # 오타는 db 방식으로는 못 찾는다
    assert es.calls == []


def test_es_adds_typo_match(env, monkeypatch) -> None:  # noqa: ANN001
    client, _, _ = env
    es = use(monkeypatch, "es", FakeEs(ids=[119133]))
    assert ids(client, "elden rnig") == [119133]
    call = es.calls[0]
    assert call["index"] == "games,game_aliases"  # 게임 + 별칭 인덱스를 한 번에
    assert call["ignore_unavailable"] is True  # 별칭 인덱스가 없어도 오류 아님
    assert call["source_includes"] == ["game_id"]
    assert "alias^2" in str(call["query"])


def test_es_query_excludes_all_llm_aliases(env, monkeypatch) -> None:  # noqa: ANN001
    client, _, _ = env
    es = use(monkeypatch, "es", FakeEs(ids=[119133]))
    ids(client, "엘든링")
    # 검수 여부(reviewed)와 상관없이 source=llm이면 뺀다
    assert es.calls[0]["query"]["bool"]["must_not"] == [{"term": {"source": "llm"}}]


def test_es_keeps_substring_matches_and_orders_by_es_score(env, monkeypatch) -> None:  # noqa: ANN001
    client, _, _ = env
    # "e"는 Five·Seven·Elden Ring 모두 부분 일치. ES 점수 순서가 앞선다
    use(monkeypatch, "es", FakeEs(ids=[119133, 7]))
    assert ids(client, "e") == [119133, 7, 5]


def test_es_ignores_ids_missing_in_mariadb(env, monkeypatch) -> None:  # noqa: ANN001
    client, _, _ = env
    use(monkeypatch, "es", FakeEs(ids=[999999, 119133]))
    assert ids(client, "elden rnig") == [119133]


@pytest.mark.parametrize(
    "es",
    [
        FakeEs(error=EsConnectionError("down")),
        FakeEs(raw={"unexpected": True}),  # 응답 모양이 다르면
        FakeEs(raw={"hits": {"hits": [{"_source": {"game_id": "x"}}]}}),  # game_id가 숫자가 아니면
    ],
)
def test_es_failure_falls_back_to_db(env, monkeypatch, es) -> None:  # noqa: ANN001
    client, _, _ = env
    use(monkeypatch, "es", es)
    assert ids(client, "elden") == [119133]  # 500이 아니라 MariaDB 부분 일치 결과
    assert es.calls


def test_es_not_called_without_q_and_autocomplete_stays_on_db(env, monkeypatch) -> None:  # noqa: ANN001
    client, _, _ = env
    es = use(monkeypatch, "es", FakeEs(ids=[119133]))
    assert client.get("/api/games").status_code == 200
    assert client.get("/api/games/autocomplete?q=elden").status_code == 200
    assert es.calls == []
