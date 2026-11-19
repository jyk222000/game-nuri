"""raw.* 소비 → 정제 → refined.* 발행. python -m refiner.main"""

from gamenuri_common.logging import get_logger

log = get_logger("refiner")


def main() -> None:
    # TODO: Consumer(group.id="refiner") subscribe raw.* → rules 적용 → Producer refined.*
    log.info("refiner start")


if __name__ == "__main__":
    main()
