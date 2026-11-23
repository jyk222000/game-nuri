"""python -m collector.main --source igdb|itad|steam|danawa [--kind ...] [--dry-run] [--limit 20]"""

import argparse
from collections.abc import Iterable
from pathlib import Path

from gamenuri_common.logging import get_logger
from gamenuri_common.messages import RawEnvelope

from collector import producer

log = get_logger("collector")

STEAM_KINDS = ["app_details", "player_count", "review"]
ITAD_KINDS = ["price", "price_history"]
KINDS_OF = {"steam": STEAM_KINDS, "itad": ITAD_KINDS}


def _publish_all(items: Iterable[tuple[str, RawEnvelope]], dry_run: bool) -> int:
    """봉투를 모두 보낸다. 수집 중 예외가 나도 이미 낸 것은 비우고, 전송 실패는 DeliveryError."""
    sent = 0
    try:
        for key, env in items:
            producer.publish(env, key, dry_run=dry_run)
            sent += 1
    except BaseException:
        producer.flush(raise_on_failure=False)  # 원래 예외를 가리지 않는다
        raise
    producer.flush()
    return sent


def run_igdb(args: argparse.Namespace) -> int:
    from collector.sources import igdb

    ids = igdb.load_game_ids(args.games_file or igdb.DEFAULT_GAMES_FILE, args.limit)
    log.info("IGDB 대상 게임 %d건", len(ids))
    return _publish_all(igdb.collect(ids), args.dry_run)


def run_itad(args: argparse.Namespace) -> int:
    from collector.sources import itad

    targets = itad.load_targets(args.games_file or itad.DEFAULT_GAMES_FILE, args.limit)
    kind = args.kind or "price"
    log.info("ITAD(%s) 대상 게임 %d건", kind, len(targets))
    if kind == "price_history":
        since = itad.since_from_days(args.since_days)
        log.info("가격 이력 since=%s", since)
        return _publish_all(itad.collect_history(targets, since=since), args.dry_run)
    return _publish_all(itad.collect(targets), args.dry_run)


def run_steam(args: argparse.Namespace) -> int:
    from collector.sources import steam

    appids = steam.load_appids(args.games_file or steam.DEFAULT_GAMES_FILE, args.limit)
    log.info("Steam(%s) 대상 게임 %d건", args.kind, len(appids))
    if args.kind == "app_details":
        items = steam.collect_app_details(appids)
    elif args.kind == "player_count":
        items = steam.collect_player_counts(appids)
    else:
        state = steam.ReviewState(args.state_file or steam.DEFAULT_STATE_FILE)
        items = steam.collect_reviews(appids, state=state, max_reviews=args.max_reviews)
        sent = _publish_all(items, args.dry_run)
        state.save()  # 전송 성공을 확인한 뒤에만 "여기까지 받았다"를 기록한다
        return sent
    return _publish_all(items, args.dry_run)


def run_danawa(args: argparse.Namespace) -> int:
    from collector.sources import danawa

    queries = danawa.load_queries(args.games_file or danawa.DEFAULT_GAMES_FILE, args.limit)
    log.info("다나와 검색 %d건 (요청 간격 10초 이상이라 오래 걸린다)", len(queries))
    return _publish_all(danawa.collect(queries), args.dry_run)


RUNNERS = {"igdb": run_igdb, "itad": run_itad, "steam": run_steam, "danawa": run_danawa}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=["itad", "igdb", "steam", "danawa"], required=True)
    ap.add_argument(
        "--kind",
        choices=sorted({k for ks in KINDS_OF.values() for k in ks}),
        help="steam(app_details|player_count|review), itad(price|price_history, 기본 price)",
    )
    ap.add_argument(
        "--since-days",
        type=int,
        help="itad price_history: 최근 N일 이력만 (주 1회 수집은 14 권장, 없으면 전체 이력)",
    )
    ap.add_argument("--dry-run", action="store_true", help="Kafka 대신 samples/에 저장")
    ap.add_argument("--limit", type=int, help="앞에서 N개 게임만 (시험용)")
    ap.add_argument("--games-file", type=Path, help="게임 목록 CSV (기본: games_1000.csv)")
    ap.add_argument(
        "--max-reviews", type=int, default=500, help="steam review: 게임당 새 리뷰 상한"
    )
    ap.add_argument("--state-file", type=Path, help="steam review: 수집 위치 파일")
    args = ap.parse_args()
    if args.source == "steam" and not args.kind:
        ap.error("--source steam 은 --kind (app_details|player_count|review) 가 필요하다")
    if args.kind and args.kind not in KINDS_OF.get(args.source, []):
        ap.error(f"--kind {args.kind} 는 --source {args.source} 에서 쓸 수 없다")
    log.info("collect start source=%s kind=%s dry_run=%s", args.source, args.kind, args.dry_run)
    runner = RUNNERS.get(args.source)
    if runner is None:
        raise SystemExit(f"{args.source} 수집기는 아직 구현 전이다")
    try:
        n = runner(args)
    except producer.DeliveryError as e:
        log.error("collect FAILED source=%s: %s", args.source, e)
        raise SystemExit(1) from e
    log.info("collect done source=%s messages=%d", args.source, n)


if __name__ == "__main__":
    main()
