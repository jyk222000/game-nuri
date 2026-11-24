"""목표가 알림 메일 발송(NW2-74, ③). 실행은 `python -m app.jobs.send_alerts`(주기 작업).

규칙
- 대상: 켜져 있는(active) 알림 중, 사용자의 메일 수신이 꺼져 있지 않은 것(행이 없으면 켜짐).
- 조건: 게임의 현재가(카드와 같은 PC 우선 새 상품 최저가)가 목표가 이하일 때.
- 중복: 마지막으로 보낸 가격(`alert_logs`)보다 **더 낮아졌을 때만** 다시 보낸다. 같은 가격이면
  다시 보내지 않는다. 겹쳐 돌아도 두 번 나가지 않게 Valkey `alert_sent:{alert_id}:{가격}`를
  먼저 잡는다(SET NX). 메일 발송이 실패하면 키를 풀어 다음 실행에서 다시 시도한다.
- 알림은 보낸 뒤에도 켜 둔다(사용자가 끄거나 지운다).
- 한계: 가격이 목표가 위로 올랐다가 같은 가격으로 내려온 경우는 새 알림으로 보지 않는다.

로그에는 메일 주소·비밀번호를 남기지 않는다.
"""

import contextlib
import logging
import smtplib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from email.message import EmailMessage
from email.utils import formataddr
from typing import Protocol

import redis
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.clients.valkey import get_valkey
from app.core.config import BackendSettings, get_backend_settings
from app.core.keys import ALERT_SENT_TTL_SECONDS, alert_sent_key
from app.db.models import Alert, AlertLog, NotificationSetting, User
from app.services import cards

log = logging.getLogger(__name__)

MAX_PER_RUN = 200  # 한 번에 보내는 메일 수 상한(설정 실수로 한꺼번에 나가는 것을 막는다)
SMTP_TIMEOUT_SECONDS = 20


class MailConfigError(RuntimeError):
    """SMTP 설정이 비어 있다 (값이 아니라 환경 변수 이름만 알려 준다)."""


@dataclass
class DueAlert:
    alert_id: int
    user_id: int
    email: str
    nickname: str | None
    game_id: int
    game_name: str
    target_price_krw: int
    price_krw: int
    store: str


@dataclass
class RunResult:
    due: int = 0
    sent: int = 0
    skipped: int = 0  # 다른 실행이 이미 처리했거나 상한 초과
    failed: int = 0


class Mailer(Protocol):
    def send(self, message: EmailMessage) -> None: ...


class SmtpMailer:
    """한 번 연결해 여러 통을 보낸다. `with`로 쓴다."""

    def __init__(self, settings: BackendSettings) -> None:
        self._s = settings
        self._conn: smtplib.SMTP | None = None

    def __enter__(self) -> "SmtpMailer":
        s = self._s
        conn = smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=SMTP_TIMEOUT_SECONDS)
        conn.starttls()
        conn.login(s.smtp_user, s.smtp_password)
        self._conn = conn
        return self

    def __exit__(self, *exc: object) -> None:
        if self._conn is not None:
            with contextlib.suppress(smtplib.SMTPException):
                self._conn.quit()

    def send(self, message: EmailMessage) -> None:
        assert self._conn is not None
        self._conn.send_message(message)


def check_config(s: BackendSettings) -> None:
    missing = [
        name
        for name, value in (
            ("SMTP_HOST", s.smtp_host),
            ("SMTP_USER", s.smtp_user),
            ("SMTP_PASSWORD", s.smtp_password),
        )
        if not value
    ]
    if missing:
        raise MailConfigError("비어 있는 설정: " + ", ".join(missing))


def sender(s: BackendSettings) -> str:
    """From 헤더 값. 이름이 있으면 `이름 <주소>`(한글은 자동 인코딩)."""
    address = s.mail_from or s.smtp_user
    name = " ".join(s.mail_from_name.split())  # 줄바꿈이 섞이지 않게
    return formataddr((name, address)) if name else address


def _one_line(text: str) -> str:
    """메일 제목에 줄바꿈이 섞이지 않게 한다."""
    return " ".join(text.split())


def _won(value: int) -> str:
    return f"{value:,}원"


def build_message(due: DueAlert, s: BackendSettings, *, test: bool = False) -> EmailMessage:
    msg = EmailMessage()
    prefix = "[테스트] " if test else ""
    msg["Subject"] = _one_line(f"{prefix}[겜누리] {due.game_name} 가격이 목표가에 도달했어요")
    msg["From"] = sender(s)
    msg["To"] = due.email
    lines = [
        f"{due.nickname or '회원'}님, 목표가 알림이에요.",
        "",
        f"{_one_line(due.game_name)} 가격이 설정한 목표가 이하가 됐어요.",
        f"- 현재가: {_won(due.price_krw)} ({due.store})",
        f"- 목표가: {_won(due.target_price_krw)}",
    ]
    base = s.public_base_url.rstrip("/")
    if base:
        lines += ["", f"{base}/games/{due.game_id}"]
    lines += ["", "메일을 그만 받으려면 마이페이지에서 메일 수신을 끄거나 알림을 지워 주세요."]
    msg.set_content("\n".join(lines))
    return msg


def find_due(db: Session) -> list[DueAlert]:
    """지금 보내야 하는 알림 목록."""
    found = db.execute(
        select(Alert, User, NotificationSetting.email_enabled)
        .join(User, User.user_id == Alert.user_id)
        .outerjoin(NotificationSetting, NotificationSetting.user_id == Alert.user_id)
        .where(Alert.active.is_(True))
        .order_by(Alert.alert_id)
    ).all()
    rows = [(a, u) for a, u, enabled in found if enabled is None or enabled]
    if not rows:
        return []
    game_ids = [a.game_id for a, _ in rows]
    prices = cards.lowest_new_prices(db, game_ids)
    games = cards.games_by_id(db, game_ids)
    last_log = select(func.max(AlertLog.log_id)).group_by(AlertLog.alert_id).scalar_subquery()
    last_price = {
        alert_id: price
        for alert_id, price in db.execute(
            select(AlertLog.alert_id, AlertLog.price_krw).where(AlertLog.log_id.in_(last_log))
        )
    }
    due: list[DueAlert] = []
    for alert, user in rows:
        row = prices.get(alert.game_id)
        game = games.get(alert.game_id)
        if row is None or game is None or row.price_krw > alert.target_price_krw:
            continue
        previous = last_price.get(alert.alert_id)
        if previous is not None and row.price_krw >= previous:
            continue  # 이미 이 가격(또는 더 싼 가격)으로 알렸다
        due.append(
            DueAlert(
                alert_id=alert.alert_id,
                user_id=user.user_id,
                email=user.email,
                nickname=user.nickname,
                game_id=alert.game_id,
                game_name=cards.game_name(game),
                target_price_krw=alert.target_price_krw,
                price_krw=row.price_krw,
                store=row.store,
            )
        )
    return due


def _claim(alert_id: int, price_krw: int) -> bool:
    """같은 (알림, 가격)을 다른 실행이 이미 잡았으면 False. Valkey가 안 되면 DB 기록만 믿고 진행."""
    try:
        return bool(
            get_valkey().set(
                alert_sent_key(alert_id, price_krw), "1", nx=True, ex=ALERT_SENT_TTL_SECONDS
            )
        )
    except redis.RedisError as exc:
        log.warning("알림 중복 방지 키 사용 불가, DB 기록만 확인: %s", type(exc).__name__)
        return True


def _release(alert_id: int, price_krw: int) -> None:
    with contextlib.suppress(redis.RedisError):
        get_valkey().delete(alert_sent_key(alert_id, price_krw))


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def send_due(
    db: Session,
    mailer: Mailer,
    settings: BackendSettings,
    due: list[DueAlert],
    claim: Callable[[int, int], bool] = _claim,
) -> RunResult:
    result = RunResult(due=len(due))
    for item in due[:MAX_PER_RUN]:
        if not claim(item.alert_id, item.price_krw):
            result.skipped += 1
            continue
        try:
            mailer.send(build_message(item, settings))
        except (smtplib.SMTPException, OSError) as exc:
            log.error("알림 메일 발송 실패 alert_id=%s: %s", item.alert_id, type(exc).__name__)
            _release(item.alert_id, item.price_krw)  # 다음 실행에서 다시 시도
            result.failed += 1
            continue
        db.add(
            AlertLog(
                alert_id=item.alert_id,
                price_krw=item.price_krw,
                store=item.store,
                sent_at=_now(),
            )
        )
        db.commit()
        result.sent += 1
    if len(due) > MAX_PER_RUN:
        rest = len(due) - MAX_PER_RUN
        result.skipped += rest
        log.warning(
            "한 번에 보내는 상한(%s)을 넘어 %s건은 다음 실행으로 넘깁니다", MAX_PER_RUN, rest
        )
    return result


def run(db: Session, settings: BackendSettings | None = None) -> RunResult:
    s = settings or get_backend_settings()
    check_config(s)
    due = find_due(db)
    if not due:
        return RunResult()
    with SmtpMailer(s) as mailer:
        return send_due(db, mailer, s, due)


def sample_due(to: str) -> DueAlert:
    """`--test-to`용 예시 한 통. DB와 무관하다."""
    return DueAlert(
        alert_id=0,
        user_id=0,
        email=to,
        nickname="테스트",
        game_id=119133,
        game_name="엘든 링",
        target_price_krw=40000,
        price_krw=38900,
        store="Steam",
    )
