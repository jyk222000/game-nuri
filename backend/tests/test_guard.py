"""읽기 전용 테이블 쓰기 가드: 가격·게임 모델은 add·update·delete 하면 flush에서 예외."""

from datetime import datetime

import pytest
from app.db.base import Base
from app.db.guard import ALLOW_READONLY_WRITE, ReadOnlyTableWriteError
from app.db.models import READ_ONLY_MODELS, Game, PriceCurrent, User
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

NOW = datetime(2026, 11, 23)


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _game(game_id: int = 1) -> Game:
    return Game(game_id=game_id, name="Elden Ring", updated_at=NOW)


def test_add_is_blocked(session: Session) -> None:
    session.add(_game())
    with pytest.raises(ReadOnlyTableWriteError, match="games"):
        session.flush()


def test_update_and_delete_are_blocked(session: Session) -> None:
    session.info[ALLOW_READONLY_WRITE] = True  # 테스트 데이터 준비
    game = _game()
    session.add(game)
    session.commit()
    session.info[ALLOW_READONLY_WRITE] = False

    game.name = "changed"
    with pytest.raises(ReadOnlyTableWriteError, match="수정"):
        session.flush()
    session.rollback()

    session.delete(session.get(Game, 1))
    with pytest.raises(ReadOnlyTableWriteError, match="삭제"):
        session.flush()


def test_price_tables_are_blocked_too(session: Session) -> None:
    session.add(
        PriceCurrent(
            game_id=1,
            store="steam",
            edition="digital",
            platform="PC",
            item_condition="new",
            price_krw=100,
            collected_at=NOW,
        )
    )
    with pytest.raises(ReadOnlyTableWriteError, match="prices_current"):
        session.commit()


def test_reading_and_unchanged_objects_are_fine(session: Session) -> None:
    session.info[ALLOW_READONLY_WRITE] = True
    session.add(_game())
    session.commit()
    session.info[ALLOW_READONLY_WRITE] = False

    game = session.get(Game, 1)
    game.name = game.name  # 값이 같으면 수정으로 보지 않는다
    session.flush()
    assert session.get(Game, 1).name == "Elden Ring"


def test_writable_tables_are_not_blocked(session: Session) -> None:
    session.add(User(email="a@example.com", created_at=NOW))
    session.commit()  # 예외 없음


def test_every_read_only_model_is_covered() -> None:
    assert len(READ_ONLY_MODELS) == 22


def test_direct_sql_is_not_caught_known_limit(session: Session) -> None:
    # 알려진 한계: 직접 SQL은 가드가 잡지 못한다. 진짜 방어선은 DB 권한이다.
    session.execute(text("INSERT INTO platforms (platform, display_name) VALUES ('PC', 'PC')"))
    session.commit()
