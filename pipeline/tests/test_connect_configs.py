"""Kafka Connect 설정이 메시지 형식(docs/contracts)·ERD·토픽 스크립트와 맞는지 확인한다."""

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MSG = ROOT / "docs/contracts/messages"
CONNECT = ROOT / "pipeline/connect"
ERD = (ROOT / "docs/contracts/erd.sql").read_text(encoding="utf-8")
SKIP = {"PRIMARY", "UNIQUE", "INDEX", "KEY", "CONSTRAINT", "FOREIGN"}


def _tables() -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for name, body in re.findall(r"CREATE TABLE `?(\w+)`?\s*\((.*?)\n\)", ERD, re.S):
        cols = set()
        for line in body.splitlines():
            m = re.match(r"\s*`?(\w+)`?\s+\S", line.split("--")[0])
            if m and m.group(1).upper() not in SKIP:
                cols.add(m.group(1))
        out[name] = cols
    return out


def _contracts() -> dict[str, dict]:
    """토픽 → {table, pk, fields}. refined.links.json(14개) + 단독 파일 4개."""
    out = {}
    links = json.loads((MSG / "refined.links.json").read_text(encoding="utf-8"))["topics"]
    for v in links.values():
        out[v["topic"]] = {
            "table": v["table"],
            "pk": v["pk.fields"].split(","),
            "fields": [f["field"] for f in v["schema"]["fields"]],
        }
    single = {
        "refined.games": ("games", ["game_id"]),
        "refined.prices": (
            "prices_current",
            ["game_id", "store", "edition", "platform", "item_condition"],
        ),
        "refined.requirements": ("game_requirements", ["game_id"]),
        "refined.review_summary": ("review_summaries", ["game_id"]),
    }
    optional = {  # 계약 PR이 먼저 merge되지 않았을 수 있다
        "refined.games_steam": ("games", ["game_id"]),
        "refined.price_history": ("price_history", []),
        "refined.review_stats": ("game_review_stats", ["game_id"]),
    }
    for topic, spec in optional.items():
        if (MSG / f"{topic}.json").exists():
            single[topic] = spec
    for topic, (table, pk) in single.items():
        ex = json.loads((MSG / f"{topic}.json").read_text(encoding="utf-8"))
        out[topic] = {
            "table": table,
            "pk": pk,
            "fields": [f["field"] for f in ex["schema"]["fields"]],
        }
    return out


TABLES = _tables()
CONTRACTS = _contracts()
JDBC = {
    f.stem: json.loads(f.read_text(encoding="utf-8"))["config"]
    for f in CONNECT.glob("jdbc-sink-*.json")
}


def test_contract_fields_exist_in_tables():
    for topic, c in CONTRACTS.items():
        missing = set(c["fields"]) - TABLES[c["table"]]
        assert not missing, f"{topic}: 테이블 {c['table']}에 없는 필드 {missing}"


def test_every_refined_topic_has_jdbc_sink():
    covered = {t for c in JDBC.values() for t in c["topics"].split(",")}
    assert set(CONTRACTS) <= covered, f"커넥터가 없는 토픽: {set(CONTRACTS) - covered}"


@pytest.mark.parametrize("name", sorted(JDBC))
def test_jdbc_sink_matches_contract(name):
    c = JDBC[name]
    assert c["dialect.name"] == "MySqlDatabaseDialect"
    assert c["auto.create"] == "false"
    assert c["value.converter.schemas.enable"] == "true"
    topics = c["topics"].split(",")
    if c.get("pk.fields") == "":  # 연결 테이블: 모든 필드가 기본 키, 토픽 이름 → 테이블 이름
        assert c["transforms.route.type"].endswith("RegexRouter")
        for t in topics:
            assert CONTRACTS[t]["pk"] == CONTRACTS[t]["fields"], t
            assert CONTRACTS[t]["table"] == t.removeprefix("refined.")
        return
    assert len(topics) == 1
    contract = CONTRACTS.get(topics[0])
    if contract is None:  # 계약 파일이 아직 main에 없음
        pytest.skip(f"{topics[0]} 메시지 형식이 아직 main에 없음")
    if c["table.name.format"] == "price_history":
        # 정제기가 ITAD 이력 + 가격이 바뀐 때만 보낸다. 자동 번호 id라 pk 없이 insert
        assert topics == ["refined.price_history"]
        assert c["insert.mode"] == "insert" and "pk.fields" not in c
    elif c["insert.mode"] == "update":
        # games_steam: 이미 있는 games 줄의 Steam 칸만 바꾼다
        assert c["table.name.format"] == contract["table"]
        assert c["pk.fields"].split(",") == contract["pk"]
    else:
        assert c["table.name.format"] == contract["table"]
        assert c["insert.mode"] == "upsert"
        assert c["pk.fields"].split(",") == contract["pk"]
    ts = c.get("transforms.ts.field")
    if ts:
        assert ts in contract["fields"]
        # 'X'(시간대)를 넣지 않는다: SimpleDateFormat은 패턴 뒤에 남는 글자(소수 초, Z)를 무시하고
        # TimestampConverter가 UTC로 읽는다. 수집기는 …27.029971Z 처럼 소수 초를 보낸다.
        assert c["transforms.ts.format"] == "yyyy-MM-dd'T'HH:mm:ss"


def test_topics_in_create_script():
    script = (ROOT / "infra/kafka/create-topics.sh").read_text(encoding="utf-8")
    for topic in CONTRACTS:
        assert re.search(rf"(?<![\w.]){re.escape(topic)}(?!\w)", script), topic


def test_connector_json_is_valid_and_named():
    for f in CONNECT.glob("*.json"):
        d = json.loads(f.read_text(encoding="utf-8"))
        assert d["name"] == f.stem


def test_mongo_sink_reviews_only_reviews_once():
    c = json.loads((CONNECT / "mongo-sink-reviews.json").read_text(encoding="utf-8"))["config"]
    assert c["topics"] == "raw.steam"
    assert c["transforms"].split(",")[0] == "onlyReview"  # 거른 뒤에 필드 추가
    assert c["transforms.onlyReview.filter.condition"] == "$[?(@.kind == 'review')]"
    assert c["transforms.onlyReview.filter.type"] == "include"
    assert c["document.id.strategy.partial.value.projection.list"] == "payload.recommendationid"
    assert c["writemodel.strategy"].endswith("ReplaceOneBusinessKeyStrategy")
