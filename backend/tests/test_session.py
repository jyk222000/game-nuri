from app.db import session as db
from sqlalchemy import create_engine, text


def test_read_falls_back_to_primary_when_replica_fails(monkeypatch) -> None:  # noqa: ANN001
    broken = create_engine("sqlite:////nonexistent-dir/replica.db")  # 연결 실패
    primary = create_engine("sqlite://")
    monkeypatch.setattr(db, "get_read_engine", lambda: broken)
    monkeypatch.setattr(db, "get_write_engine", lambda: primary)

    gen = db.get_read_db()
    session = next(gen)
    assert session.get_bind() is primary
    assert session.execute(text("SELECT 1")).scalar() == 1
    gen.close()


def test_read_uses_replica_when_healthy(monkeypatch) -> None:  # noqa: ANN001
    replica = create_engine("sqlite://")
    primary = create_engine("sqlite://")
    monkeypatch.setattr(db, "get_read_engine", lambda: replica)
    monkeypatch.setattr(db, "get_write_engine", lambda: primary)

    gen = db.get_read_db()
    session = next(gen)
    assert session.get_bind() is replica
    gen.close()
