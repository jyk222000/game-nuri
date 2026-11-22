import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import verify_flow as vf  # noqa: E402


class FakeConsumer:
    def __init__(self, topics: dict[str, dict[int, tuple[int, int]]]) -> None:
        self._topics = topics

    def list_topics(self, timeout: float = 5.0):  # noqa: ANN201
        meta = {
            n: SimpleNamespace(partitions={p: None for p in parts})
            for n, parts in self._topics.items()
        }
        return SimpleNamespace(topics=meta)

    def get_watermark_offsets(self, tp, timeout: float = 5.0):  # noqa: ANN001, ANN201
        return self._topics[tp.topic][tp.partition]


def test_kafka_counts_sums_partitions_and_filters_topics() -> None:
    consumer = FakeConsumer(
        {
            "raw.itad": {0: (0, 10), 1: (5, 8)},  # 10 + 3
            "refined.prices": {0: (0, 4)},
            "clickstream": {0: (2, 2)},
            "__consumer_offsets": {0: (0, 99)},  # 제외
        }
    )
    rows = {r.target: r for r in vf.kafka_counts(consumer)}
    assert set(rows) == {"raw.itad", "refined.prices", "clickstream"}
    assert rows["raw.itad"].count == "13"
    assert rows["raw.itad"].note == "오프셋 기준, 삭제분 제외"
    assert rows["clickstream"].count == "0"


def _db(rows: dict[str, int]) -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    for table, n in rows.items():
        conn.execute(f"CREATE TABLE `{table}` (id INTEGER)")
        conn.executemany(f"INSERT INTO `{table}` VALUES (?)", [(i,) for i in range(n)])
    return conn


def test_table_counts() -> None:
    assert vf.table_counts(_db({"games": 3, "stores": 0}), ["games", "stores"]) == {
        "games": 3,
        "stores": 0,
    }


class LagConn:
    """SHOW REPLICA STATUS 응답을 흉내 낸다 (SELECT COUNT는 sqlite에 위임)."""

    def __init__(self, inner: sqlite3.Connection, lag: int | None) -> None:
        self._inner, self._lag = inner, lag

    def cursor(self):  # noqa: ANN201
        return _LagCursor(self._inner.cursor(), self._lag)


class _LagCursor:
    def __init__(self, inner, lag) -> None:  # noqa: ANN001
        self._c, self._lag, self._status = inner, lag, False
        self.description = None

    def execute(self, sql: str) -> None:
        if sql == "SHOW REPLICA STATUS":
            self._status = True
            self.description = [("Seconds_Behind_Master",)]
        elif sql == "SHOW TABLES":
            self._status = False
            self._c.execute("SELECT name FROM sqlite_master WHERE type='table'")
        else:
            self._status = False
            self._c.execute(sql)

    def fetchone(self):  # noqa: ANN201
        return (self._lag,) if self._status else self._c.fetchone()

    def fetchall(self):  # noqa: ANN201
        return self._c.fetchall()


def test_mariadb_match_and_mismatch_shows_lag() -> None:
    primary = LagConn(_db({"games": 5, "stores": 2}), None)
    replica = LagConn(_db({"games": 4, "stores": 2}), 7)
    rows = vf.mariadb_rows(lambda: primary, lambda: replica)
    by = {r.target: r for r in rows}
    assert by["stores"].note == "일치"
    assert "불일치" in by["games"].note and "Seconds_Behind_Master=7" in by["games"].note


def test_primary_failure_is_reported_and_continues() -> None:
    def boom():  # noqa: ANN202
        raise RuntimeError("down")

    rows = vf.mariadb_rows(boom, boom)
    assert [r.count for r in rows] == [vf.FAIL]


def test_replica_failure_keeps_primary_counts() -> None:
    def boom():  # noqa: ANN202
        raise RuntimeError("down")

    rows = vf.mariadb_rows(lambda: LagConn(_db({"games": 5}), None), boom)
    assert rows[0].count == "5" and rows[0].note == "Replica 연결 실패"


def test_mongo_counts() -> None:
    class Coll:
        def __init__(self, n: int) -> None:
            self.n = n

        def count_documents(self, flt: dict) -> int:
            return self.n

    class Db:
        _c = {"reviews": Coll(3), "games": Coll(1)}

        def list_collection_names(self) -> list[str]:
            return list(self._c)

        def __getitem__(self, name: str) -> Coll:
            return self._c[name]

    rows = vf.mongo_counts(Db())
    assert [(r.target, r.count) for r in rows] == [("games", "1"), ("reviews", "3")]


def test_render_has_header_and_rows() -> None:
    out = vf.render([vf.Row("MongoDB", "games", "1", "")])
    assert out.splitlines()[0].startswith("단계")
    assert "games" in out
