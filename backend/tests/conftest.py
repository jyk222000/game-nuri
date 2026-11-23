"""API 테스트 공용: SQLite 메모리 DB, 가짜 로그인, 게임 데이터 준비."""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime

import pytest
from app.api.deps import CurrentUser, get_current_user
from app.db.base import Base
from app.db.guard import ALLOW_READONLY_WRITE
from app.db.models import Game, User
from app.db.session import get_read_db, get_write_db
from app.main import app
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

NOW = datetime(2026, 11, 23)


@contextmanager
def seed(engine) -> Iterator[Session]:  # noqa: ANN001
    """가격·게임 같은 읽기 전용 테이블에 테스트 데이터를 넣는다 (쓰기 가드를 이 세션에서만 끈다)."""
    with Session(engine) as s:
        s.info[ALLOW_READONLY_WRITE] = True
        yield s
        s.commit()


@pytest.fixture
def env():
    """(client, engine, current). current["id"]로 로그인 사용자를 바꾼다. 게임 5·7·119133 준비됨."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    with seed(engine) as s:
        s.add_all(
            [
                User(user_id=1, email="a@example.com", created_at=NOW),
                User(user_id=2, email="b@example.com", created_at=NOW),
                Game(game_id=5, name="Five", updated_at=NOW),
                Game(game_id=7, name="Seven", updated_at=NOW),
                Game(game_id=119133, name="Elden Ring", name_ko="엘든 링", updated_at=NOW),
            ]
        )

    def db():
        with Session(engine) as s:
            yield s

    current = {"id": 1}
    app.dependency_overrides[get_write_db] = db
    app.dependency_overrides[get_read_db] = db  # 테스트에서는 읽기·쓰기가 같은 DB
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(user_id=current["id"])
    yield TestClient(app), engine, current
    app.dependency_overrides.clear()
