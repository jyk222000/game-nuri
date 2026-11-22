"""겜누리 - 데이터 흐름 검증: 단계별 건수를 한 번에 출력한다 (읽기 전용).

  Kafka   토픽별 메시지 수 (raw.*, refined.*, clickstream)
  MariaDB Primary·Replica 테이블별 행 수 + 일치 여부
  MongoDB 컬렉션별 문서 수

읽기만 한다: SELECT COUNT, 토픽 오프셋 조회, SHOW REPLICA STATUS, count_documents.
토픽에 메시지를 넣지 않고 컨슈머 그룹을 만들거나 오프셋을 커밋하지 않는다.
접속 정보는 shared의 Settings(.env 또는 환경 변수)에서만 읽는다.

사용법 (backend1 또는 kafka VM, 레포 루트에서)
  pip install -e shared pymysql pymongo confluent-kafka
  python scripts/verify_flow.py
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Iterable
from dataclasses import dataclass

FAIL = "연결 실패"
KAFKA_PREFIXES = ("raw.", "refined.", "clickstream")


@dataclass
class Row:
    stage: str  # 단계
    target: str  # 대상
    count: str  # 건수 (또는 "연결 실패")
    note: str = ""  # Primary·Replica 일치 여부, 복제 지연 등


# ---------- Kafka ----------
def kafka_counts(consumer, timeout: float = 5.0) -> list[Row]:  # noqa: ANN001
    """토픽별 (end_offset - beginning_offset). 그룹에 참여(subscribe)하지 않고 워터마크만 조회한다."""
    from confluent_kafka import TopicPartition

    meta = consumer.list_topics(timeout=timeout)
    rows: list[Row] = []
    for name in sorted(meta.topics):
        if not name.startswith(KAFKA_PREFIXES):
            continue
        total = 0
        for partition in meta.topics[name].partitions:
            low, high = consumer.get_watermark_offsets(
                TopicPartition(name, partition), timeout=timeout
            )
            total += high - low
        stage = "Kafka raw" if name.startswith("raw.") else "Kafka refined"
        if name == "clickstream":
            stage = "Kafka clickstream"
        rows.append(Row(stage, name, str(total), "오프셋 기준, 삭제분 제외"))
    return rows


# ---------- MariaDB ----------
def fetch_tables(conn) -> list[str]:  # noqa: ANN001
    cur = conn.cursor()
    cur.execute("SHOW TABLES")
    return sorted(r[0] for r in cur.fetchall())


def table_counts(conn, tables: Iterable[str]) -> dict[str, int]:  # noqa: ANN001
    cur = conn.cursor()
    counts: dict[str, int] = {}
    for table in tables:
        cur.execute(f"SELECT COUNT(*) FROM `{table}`")  # 테이블 이름은 SHOW TABLES 결과만 쓴다
        counts[table] = int(cur.fetchone()[0])
    return counts


def replica_lag(conn) -> str:  # noqa: ANN001
    """Replica의 Seconds_Behind_Master. 못 읽으면 '미확인'."""
    try:
        cur = conn.cursor()
        cur.execute("SHOW REPLICA STATUS")
        row = cur.fetchone()
        if row is None:
            return "미확인(복제 설정 없음)"
        cols = [d[0] for d in cur.description]
        value = dict(zip(cols, row, strict=True)).get("Seconds_Behind_Master")
        return "NULL(복제 중단?)" if value is None else str(value)
    except Exception:  # noqa: BLE001 - 권한 없음 등
        return "미확인(권한 없음?)"


def mariadb_rows(
    primary_factory: Callable[[], object], replica_factory: Callable[[], object]
) -> list[Row]:
    stage = "MariaDB"
    try:
        primary = primary_factory()
        tables = fetch_tables(primary)
        p_counts = table_counts(primary, tables)
    except Exception:  # noqa: BLE001
        return [Row(stage, "Primary", FAIL)]

    try:
        replica = replica_factory()
        r_counts = table_counts(replica, tables)
        lag = replica_lag(replica)
    except Exception:  # noqa: BLE001
        return [Row(stage, t, str(p_counts[t]), "Replica 연결 실패") for t in tables]

    rows = []
    for t in tables:
        same = p_counts[t] == r_counts.get(t)
        note = (
            "일치" if same else f"불일치 (Replica {r_counts.get(t)}, Seconds_Behind_Master={lag})"
        )
        rows.append(Row(stage, t, str(p_counts[t]), note))
    rows.append(Row(stage, "(복제 지연 Seconds_Behind_Master)", lag))
    return rows


# ---------- MongoDB ----------
def mongo_counts(db) -> list[Row]:  # noqa: ANN001
    return [
        Row("MongoDB", name, str(db[name].count_documents({})))
        for name in sorted(db.list_collection_names())
    ]


# ---------- 출력 ----------
def render(rows: list[Row]) -> str:
    header = ("단계", "대상", "건수", "비고")
    table = [header] + [(r.stage, r.target, r.count, r.note) for r in rows]
    widths = [max(len(str(line[i])) for line in table) for i in range(4)]
    lines = []
    for i, line in enumerate(table):
        lines.append(" | ".join(str(v).ljust(widths[j]) for j, v in enumerate(line)).rstrip())
        if i == 0:
            lines.append("-+-".join("-" * w for w in widths))
    return "\n".join(lines)


def main() -> int:
    from gamenuri_common.config import get_settings

    s = get_settings()
    rows: list[Row] = []

    # Kafka
    try:
        from confluent_kafka import Consumer

        consumer = Consumer(
            {
                "bootstrap.servers": s.kafka_bootstrap,
                "group.id": "verify-flow-readonly",  # subscribe·commit을 하지 않아 그룹이 생기지 않는다
                "enable.auto.commit": False,
            }
        )
        try:
            rows += kafka_counts(consumer)
        finally:
            consumer.close()
    except Exception:  # noqa: BLE001
        rows.append(Row("Kafka", s.kafka_bootstrap, FAIL))

    # MariaDB
    def connect(host: str):  # noqa: ANN202
        import pymysql  # 없으면 이 연결만 실패로 표시된다

        return pymysql.connect(
            host=host,
            port=s.mariadb_port,
            user=s.mariadb_user,
            password=s.mariadb_password,
            database=s.mariadb_db,
            connect_timeout=3,
        )

    rows += mariadb_rows(lambda: connect(s.mariadb_host), lambda: connect(s.mariadb_read_host))

    # MongoDB
    try:
        from pymongo import MongoClient

        client = MongoClient(s.mongo_uri, serverSelectionTimeoutMS=3000)
        rows += mongo_counts(client[s.mongo_db])
    except Exception:  # noqa: BLE001
        rows.append(Row("MongoDB", s.mongo_db, FAIL))

    print(render(rows))
    print("\n※ Kafka 건수는 '오프셋 기준, 삭제분 제외' (retention으로 지워진 앞부분은 빠진다).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
