"""모델 28개가 docs/contracts/erd.sql과 같은지 검사한다. erd.sql을 직접 읽어 비교한다.

비교 항목: 테이블 목록, 컬럼 이름·순서, 컬럼 타입(MariaDB 방언으로 컴파일),
NOT NULL 여부, 기본키, 인덱스·고유 키 이름.
ERD가 바뀌면 이 테스트가 먼저 실패한다.
"""

import re
from pathlib import Path

import pytest
from app.db.base import Base
from app.db.models import READ_ONLY_MODELS, WRITABLE_MODELS
from sqlalchemy.dialects import mysql

ERD = Path(__file__).resolve().parents[2] / "docs" / "contracts" / "erd.sql"
SKIP = ("CONSTRAINT", "PRIMARY", "UNIQUE", "INDEX", "KEY", "FOREIGN")
COLUMN = re.compile(r"^(\w+)\s+([A-Za-z]+(?:\([^)]*\))?)(.*)$")
TYPE_ALIASES = {"INTEGER": "INT", "BOOL": "BOOLEAN"}


def _tables() -> dict[str, dict]:
    text = ERD.read_text(encoding="utf-8")
    out: dict[str, dict] = {}
    for name, body in re.findall(r"CREATE TABLE (\w+)\s*\((.*?)\n\);", text, re.S):
        cols: list[tuple[str, str, bool]] = []  # (이름, 타입, NOT NULL)
        pk: list[str] = []
        indexes: set[str] = set()
        for raw in body.splitlines():
            line = raw.split("--")[0].strip().rstrip(",").strip()
            if not line:
                continue
            upper = line.upper()
            if upper.startswith("PRIMARY KEY"):
                pk = [c.strip() for c in line[line.index("(") + 1 : line.rindex(")")].split(",")]
            elif upper.startswith(("INDEX", "UNIQUE KEY")):
                indexes.add(line.split()[1] if upper.startswith("INDEX") else line.split()[2])
            elif upper.startswith(SKIP):
                continue
            else:
                m = COLUMN.match(line)
                assert m, f"{name}: 해석할 수 없는 줄 {line!r}"
                col, typ, rest = m.group(1), m.group(2), m.group(3).upper()
                if "PRIMARY KEY" in rest:
                    pk = [col]
                cols.append((col, typ.upper().replace(" ", ""), "NOT NULL" in rest))
        out[name] = {"columns": cols, "pk": pk, "indexes": indexes}
    return out


ERD_TABLES = _tables()
ALL_MODELS = (*WRITABLE_MODELS, *READ_ONLY_MODELS)
DIALECT = mysql.dialect()


def _norm_type(col) -> str:  # noqa: ANN001
    text = col.type.compile(dialect=DIALECT).upper().replace(" ", "")
    return TYPE_ALIASES.get(text, text)


def test_28_tables_match() -> None:
    assert len(ERD_TABLES) == 28
    assert {m.__tablename__ for m in ALL_MODELS} == set(ERD_TABLES)
    assert len(ALL_MODELS) == 28
    assert len(WRITABLE_MODELS) == 7 and len(READ_ONLY_MODELS) == 21
    assert set(Base.metadata.tables) == set(ERD_TABLES)


@pytest.mark.parametrize("model", ALL_MODELS, ids=lambda m: m.__tablename__)
def test_columns_types_keys_match(model: type[Base]) -> None:
    erd = ERD_TABLES[model.__tablename__]
    table = model.__table__
    assert [c.name for c in table.columns] == [c[0] for c in erd["columns"]]
    for column, (name, typ, not_null) in zip(table.columns, erd["columns"], strict=True):
        assert _norm_type(column) == typ, f"{table.name}.{name} 타입"
        is_pk = name in erd["pk"]
        assert (not column.nullable) == (not_null or is_pk), f"{table.name}.{name} NOT NULL"
    assert {c.name for c in table.primary_key.columns} == set(erd["pk"])


def test_price_keys_include_platform_and_condition() -> None:
    assert set(ERD_TABLES["prices_current"]["pk"]) == {
        "game_id",
        "store",
        "edition",
        "platform",
        "item_condition",
    }


def test_price_history_has_no_unique_key() -> None:
    from app.db.models import PriceHistory

    assert [c.name for c in PriceHistory.__table__.primary_key.columns] == ["id"]
    assert not [
        c for c in PriceHistory.__table__.constraints if c.__class__.__name__ == "UniqueConstraint"
    ]


@pytest.mark.parametrize("model", ALL_MODELS, ids=lambda m: m.__tablename__)
def test_index_names_match(model: type[Base]) -> None:
    table = model.__table__
    have = {i.name for i in table.indexes} | {c.name for c in table.constraints if c.name}
    assert ERD_TABLES[table.name]["indexes"] <= have
