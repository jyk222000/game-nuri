"""python -m collector.main --source itad [--dry-run]"""

import argparse

from gamenuri_common.logging import get_logger

log = get_logger("collector")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=["itad", "igdb", "steam", "danawa"], required=True)
    ap.add_argument("--dry-run", action="store_true", help="Kafka 대신 samples/에 저장")
    args = ap.parse_args()
    log.info("collect start source=%s dry_run=%s", args.source, args.dry_run)
    # TODO: sources.<source>.collect() → producer.publish()


if __name__ == "__main__":
    main()
