"""사용자 모델이 docs/contracts/erd.sql과 같은지 검사한다 (erd.sql을 직접 읽어 비교)."""

import re
from datetime import datetime
from pathlib import Path

import pytest
from app.db.base import Base
from app.db.models import WRITABLE_MODELS, Alert, User, Wishlist
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

ERD = Path(__file__).resolve().parents[2] / "docs" / "contracts" / "erd.sql"
SKIP = ("CONSTRAINT", "PRIMARY", "UNIQUE", "INDEX", "KEY", "FOREIGN")


def erd_columns(table: str) -> list[str]:
    text = ERD.read_text(encoding="utf-8")
    block = re.search(rf"CREATE TABLE {table}\s*\((.*?)\n\);", text, re.S)
    assert block, f"{table} not found in erd.sql"
    cols = []
    for line in block.group(1).splitlines():
        line = line.split("--")[0].strip()
        if not line or line.upper().startswith(SKIP):
            continue
        cols.append(line.split()[0])
    return cols


@pytest.mark.parametrize("model", WRITABLE_MODELS, ids=lambda m: m.__tablename__)
def test_columns_match_erd(model: type[Base]) -> None:
    assert [c.name for c in model.__table__.columns] == erd_columns(model.__tablename__)


def test_seven_writable_tables() -> None:
    assert {m.__tablename__ for m in WRITABLE_MODELS} == {
        "users",
        "user_specs",
        "notification_settings",
        "wishlists",
        "alerts",
        "alert_logs",
        "user_owned_games",
    }


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def test_insert_and_defaults(session: Session) -> None:
    now = datetime(2026, 11, 22, 3, 0, 0)
    user = User(email="a@example.com", created_at=now)
    session.add(user)
    session.flush()
    assert user.user_id is not None

    session.add_all(
        [
            Wishlist(user_id=user.user_id, game_id=119133, created_at=now),
            Alert(user_id=user.user_id, game_id=119133, target_price_krw=30000, created_at=now),
        ]
    )
    session.commit()
    alert = session.scalars(select(Alert)).one()
    assert alert.active is True  # 기본값 TRUE


def test_alert_unique_per_user_game(session: Session) -> None:
    from sqlalchemy.exc import IntegrityError

    now = datetime(2026, 11, 22)
    user = User(email="b@example.com", created_at=now)
    session.add(user)
    session.flush()
    session.add(Alert(user_id=user.user_id, game_id=1, target_price_krw=100, created_at=now))
    session.commit()
    session.add(Alert(user_id=user.user_id, game_id=1, target_price_krw=200, created_at=now))
    with pytest.raises(IntegrityError):
        session.commit()
