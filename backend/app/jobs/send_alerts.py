"""목표가 알림 메일 발송 명령. systemd 타이머가 주기적으로 실행한다.

  python -m app.jobs.send_alerts                  # 조건이 맞는 알림에 실제로 메일을 보낸다
  python -m app.jobs.send_alerts --dry-run        # 누구에게 무엇을 보낼지만 출력, 보내지 않는다
  python -m app.jobs.send_alerts --test-to 주소   # 예시 메일 한 통을 그 주소로만 보낸다(DB 안 씀)

종료 코드: 0 정상, 1 일부 발송 실패, 2 설정 오류.
"""

import argparse
import logging
import sys

from gamenuri_common.config import get_settings
from sqlalchemy.orm import sessionmaker

from app.core.config import get_backend_settings
from app.db.session import get_write_engine
from app.services import alert_mail

log = logging.getLogger("send_alerts")


def _mask(email: str) -> str:
    name, _, domain = email.partition("@")
    return f"{name[:1]}***@{domain}"


def _test_mail(to: str) -> int:
    s = get_backend_settings()
    alert_mail.check_config(s)
    message = alert_mail.build_message(alert_mail.sample_due(to), s, test=True)
    with alert_mail.SmtpMailer(s) as mailer:
        mailer.send(message)
    print(f"예시 메일 1통 발송 완료 → {_mask(to)}")
    return 0


def _dry_run() -> int:
    with sessionmaker(bind=get_write_engine(), expire_on_commit=False)() as db:
        due = alert_mail.find_due(db)
    print(f"보낼 알림 {len(due)}건 (실제로는 보내지 않음)")
    for d in due[: alert_mail.MAX_PER_RUN]:
        print(
            f"  alert_id={d.alert_id} game_id={d.game_id} 현재가={d.price_krw} "
            f"목표가={d.target_price_krw} → {_mask(d.email)}"
        )
    return 0


def _send() -> int:
    with sessionmaker(bind=get_write_engine(), expire_on_commit=False)() as db:
        result = alert_mail.run(db)
    log.info(
        "알림 메일: 대상 %s건, 발송 %s건, 건너뜀 %s건, 실패 %s건",
        result.due,
        result.sent,
        result.skipped,
        result.failed,
    )
    return 1 if result.failed else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="목표가 알림 메일 발송")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--dry-run", action="store_true", help="보내지 않고 대상만 출력")
    group.add_argument("--test-to", metavar="ADDRESS", help="예시 메일 한 통을 이 주소로만 발송")
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=get_settings().log_level, format="%(asctime)s %(levelname)s %(message)s"
    )
    try:
        if args.test_to:
            return _test_mail(args.test_to)
        if args.dry_run:
            return _dry_run()
        return _send()
    except alert_mail.MailConfigError as exc:
        log.error("%s (backend.env를 확인하세요)", exc)
        return 2


if __name__ == "__main__":
    sys.exit(main())
