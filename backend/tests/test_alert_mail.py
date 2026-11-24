"""목표가 알림 메일(NW2-74). SMTP·Valkey는 가짜, DB는 SQLite 메모리. 실제 메일은 보내지 않는다."""

import smtplib

import pytest
from app.core import config
from app.db.models import Alert, AlertLog, NotificationSetting, PriceCurrent
from app.jobs import send_alerts
from app.services import alert_mail
from sqlalchemy.orm import Session

from tests.conftest import NOW, seed


class FakeMailer:
    def __init__(self, fail: bool = False) -> None:
        self.sent: list = []
        self.fail = fail

    def send(self, message) -> None:  # noqa: ANN001
        if self.fail:
            raise smtplib.SMTPException("down")
        self.sent.append(message)


class FakeValkey:
    def __init__(self) -> None:
        self.keys: dict[str, str] = {}

    def set(self, key, value, nx=False, ex=None):  # noqa: ANN001
        if nx and key in self.keys:
            return None
        self.keys[key] = value
        return True

    def delete(self, key) -> None:  # noqa: ANN001
        self.keys.pop(key, None)


def _settings(**over) -> config.BackendSettings:  # noqa: ANN003
    values = dict(
        smtp_user="sender@example.com",
        smtp_password="pw-not-real",
        public_base_url="https://example.test",
    )
    values.update(over)
    return config.BackendSettings(_env_file=None, **values)


def _price(game_id: int, price: int, platform: str = "PC", store: str = "Steam") -> PriceCurrent:
    return PriceCurrent(
        game_id=game_id,
        store=store,
        edition="digital",
        platform=platform,
        item_condition="new",
        price_krw=price,
        collected_at=NOW,
    )


@pytest.fixture
def mail(env, monkeypatch):  # noqa: ANN001
    """(engine, valkey). 알림: 사용자 1 → 게임 7, 목표 40000. 게임 7 현재가 38900."""
    _, engine, _ = env
    valkey = FakeValkey()
    monkeypatch.setattr(alert_mail, "get_valkey", lambda: valkey)
    with seed(engine) as s:
        s.add_all(
            [
                Alert(alert_id=1, user_id=1, game_id=7, target_price_krw=40000, created_at=NOW),
                _price(7, 38900),
            ]
        )
    return engine, valkey


def _due(engine) -> list[alert_mail.DueAlert]:  # noqa: ANN001
    with Session(engine) as db:
        return alert_mail.find_due(db)


def _send(engine, mailer, valkey=None, **over):  # noqa: ANN001, ANN003
    with Session(engine) as db:
        due = alert_mail.find_due(db)
        return alert_mail.send_due(db, mailer, _settings(**over), due)


def test_sends_when_price_reaches_target_and_logs_it(mail) -> None:  # noqa: ANN001
    engine, valkey = mail
    mailer = FakeMailer()
    result = _send(engine, mailer)
    assert (result.due, result.sent, result.failed) == (1, 1, 0)
    msg = mailer.sent[0]
    assert msg["To"] == "a@example.com" and msg["From"] == "sender@example.com"
    assert "Seven" in msg["Subject"]
    body = msg.get_content()
    assert "38,900원" in body and "40,000원" in body and "https://example.test/games/7" in body
    with Session(engine) as db:
        log = db.query(AlertLog).one()
        assert (log.alert_id, log.price_krw, log.store) == (1, 38900, "Steam")
    assert "alert_sent:1:38900" in valkey.keys


def test_not_sent_when_price_is_above_target(mail) -> None:  # noqa: ANN001
    engine, _ = mail
    with Session(engine) as db:
        db.query(Alert).update({"target_price_krw": 30000})
        db.commit()
    assert _due(engine) == []


def test_same_price_is_not_sent_twice_but_lower_price_is(mail) -> None:  # noqa: ANN001
    engine, valkey = mail
    mailer = FakeMailer()
    _send(engine, mailer)
    assert _due(engine) == []  # 같은 가격이면 다시 보내지 않는다
    valkey.keys.clear()  # Valkey 키가 만료됐어도 DB 기록으로 막는다
    assert _due(engine) == []
    with Session(engine) as db:
        db.query(PriceCurrent).update({"price_krw": 35000})
        db.commit()
    again = _send(engine, mailer)
    assert again.sent == 1 and len(mailer.sent) == 2  # 더 내려가면 다시 보낸다
    assert "35,000원" in mailer.sent[1].get_content()


def test_inactive_and_email_disabled_are_skipped(mail) -> None:  # noqa: ANN001
    engine, _ = mail
    with Session(engine) as db:
        db.add_all(
            [
                Alert(alert_id=2, user_id=2, game_id=7, target_price_krw=40000, created_at=NOW),
                NotificationSetting(user_id=2, email_enabled=False, updated_at=NOW),
            ]
        )
        db.query(Alert).filter(Alert.alert_id == 1).update({"active": False})
        db.commit()
    assert _due(engine) == []  # 1번은 꺼진 알림, 2번은 메일 수신을 끈 사용자


def test_missing_notification_row_means_enabled(mail) -> None:  # noqa: ANN001
    engine, _ = mail
    assert [d.alert_id for d in _due(engine)] == [1]  # notification_settings 행이 없어도 보낸다


def test_pc_price_is_used_when_console_is_cheaper(mail) -> None:  # noqa: ANN001
    engine, _ = mail
    with seed(engine) as s:
        s.add(_price(7, 20000, platform="PS5", store="다나와"))
    due = _due(engine)
    assert due[0].price_krw == 38900  # 카드·구매 타이밍과 같은 PC 우선 기준


def test_failed_send_is_retried_next_time(mail) -> None:  # noqa: ANN001
    engine, valkey = mail
    result = _send(engine, FakeMailer(fail=True))
    assert (result.sent, result.failed) == (0, 1)
    assert valkey.keys == {}  # 키를 풀어 둔다
    with Session(engine) as db:
        assert db.query(AlertLog).count() == 0
    assert _send(engine, FakeMailer()).sent == 1


def test_overlapping_run_does_not_send_twice(mail) -> None:  # noqa: ANN001
    engine, valkey = mail
    valkey.keys["alert_sent:1:38900"] = "1"  # 다른 실행이 먼저 잡았다
    mailer = FakeMailer()
    result = _send(engine, mailer)
    assert (result.sent, result.skipped) == (0, 1) and mailer.sent == []


def test_subject_has_no_line_breaks(mail) -> None:  # noqa: ANN001
    due = _due(mail[0])[0]
    due.game_name = "Bad\r\nBcc: x@example.com"
    msg = alert_mail.build_message(due, _settings())
    assert "\n" not in msg["Subject"] and "\r" not in msg["Subject"]
    assert msg["Bcc"] is None


def test_missing_smtp_settings_names_only(mail) -> None:  # noqa: ANN001
    with pytest.raises(alert_mail.MailConfigError) as err:
        alert_mail.check_config(_settings(smtp_password=""))
    assert "SMTP_PASSWORD" in str(err.value) and "pw-not-real" not in str(err.value)


def test_cli_returns_2_when_smtp_not_configured(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(send_alerts, "get_backend_settings", lambda: _settings(smtp_password=""))
    assert send_alerts.main(["--test-to", "me@example.com"]) == 2


def test_test_to_sends_one_sample_without_db(monkeypatch) -> None:  # noqa: ANN001
    sent: list = []

    class Spy:
        def __init__(self, settings) -> None:  # noqa: ANN001
            pass

        def __enter__(self):  # noqa: ANN204
            return self

        def __exit__(self, *exc) -> None:  # noqa: ANN002
            pass

        def send(self, message) -> None:  # noqa: ANN001
            sent.append(message)

    monkeypatch.setattr(send_alerts, "get_backend_settings", lambda: _settings())
    monkeypatch.setattr(alert_mail, "SmtpMailer", Spy)
    assert send_alerts.main(["--test-to", "me@example.com"]) == 0
    assert len(sent) == 1 and sent[0]["To"] == "me@example.com"
    assert sent[0]["Subject"].startswith("[테스트]")
