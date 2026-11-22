"""사용자·알림 테이블 (erd.sql 3장). Backend가 직접 쓰는 테이블.

시간은 UTC DATETIME(naive)으로 저장한다. 읽기·쓰기 모두 Primary 연결을 쓴다(복제 지연).
"""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, BigIntPk


class User(Base):
    __tablename__ = "users"

    user_id: Mapped[int] = mapped_column(BigIntPk, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    password_hash: Mapped[str | None] = mapped_column(String(255))  # 구글 로그인 사용자는 NULL
    google_sub: Mapped[str | None] = mapped_column(String(64), unique=True)
    nickname: Mapped[str | None] = mapped_column(String(64))
    steam_id: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime)


class UserSpec(Base):
    __tablename__ = "user_specs"

    user_id: Mapped[int] = mapped_column(
        BigIntPk, ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True
    )
    cpu: Mapped[str | None] = mapped_column(String(128))
    gpu: Mapped[str | None] = mapped_column(String(128))
    ram_gb: Mapped[int | None] = mapped_column(Integer)
    os: Mapped[str | None] = mapped_column(String(64))
    updated_at: Mapped[datetime] = mapped_column(DateTime)


class NotificationSetting(Base):
    __tablename__ = "notification_settings"

    user_id: Mapped[int] = mapped_column(
        BigIntPk, ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True
    )
    email_enabled: Mapped[bool] = mapped_column(Boolean, server_default=true())
    updated_at: Mapped[datetime] = mapped_column(DateTime)


class UserOwnedGame(Base):
    __tablename__ = "user_owned_games"

    user_id: Mapped[int] = mapped_column(
        BigIntPk, ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True
    )
    steam_appid: Mapped[int] = mapped_column(Integer, primary_key=True)
    playtime_forever_min: Mapped[int] = mapped_column(Integer, server_default="0")
    rtime_last_played: Mapped[datetime | None] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime)


class Wishlist(Base):
    __tablename__ = "wishlists"

    user_id: Mapped[int] = mapped_column(
        BigIntPk, ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True
    )
    game_id: Mapped[int] = mapped_column(BigIntPk, primary_key=True, autoincrement=False)
    created_at: Mapped[datetime] = mapped_column(DateTime)


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (UniqueConstraint("user_id", "game_id", name="uq_user_game"),)

    alert_id: Mapped[int] = mapped_column(BigIntPk, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigIntPk, ForeignKey("users.user_id", ondelete="CASCADE"))
    game_id: Mapped[int] = mapped_column(BigIntPk)
    target_price_krw: Mapped[int] = mapped_column(Integer)
    active: Mapped[bool] = mapped_column(Boolean, server_default=true())
    created_at: Mapped[datetime] = mapped_column(DateTime)


class AlertLog(Base):
    __tablename__ = "alert_logs"

    log_id: Mapped[int] = mapped_column(BigIntPk, primary_key=True, autoincrement=True)
    alert_id: Mapped[int] = mapped_column(
        BigIntPk, ForeignKey("alerts.alert_id", ondelete="CASCADE")
    )
    price_krw: Mapped[int] = mapped_column(Integer)
    store: Mapped[str] = mapped_column(String(32))
    sent_at: Mapped[datetime] = mapped_column(DateTime)
