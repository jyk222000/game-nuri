#!/usr/bin/env bash
# 수집기 한 종류를 실행한다. systemd 서비스(collector@<이름>.service)가 부른다.
#   사용: run-collector.sh itad-price|itad-history|igdb|steam-details|steam-players|steam-reviews|steam-review-summary|danawa
# 같은 이름의 수집이 이미 돌고 있으면(예: 다나와 2~3시간짜리가 안 끝났는데 다음 시각이 옴, 또는 손으로 실행 중)
# 겹쳐 실행하지 않고 "건너뜀"만 남기고 정상 종료한다.
set -euo pipefail

NAME="${1:?수집 이름이 필요합니다 (예: itad-price)}"
REPO="${GAMENURI_REPO:-/opt/game-nuri/repo}"
PYTHON="${GAMENURI_PYTHON:-$REPO/.venv/bin/python}"
STATE_DIR="${STATE_DIRECTORY:-/var/lib/game-nuri/collector}"
LOCK_DIR="${RUNTIME_DIRECTORY:-/tmp}"

case "$NAME" in
  itad-price)           ARGS=(--source itad --kind price) ;;
  itad-history)         ARGS=(--source itad --kind price_history --since-days 14) ;;
  igdb)                 ARGS=(--source igdb) ;;
  steam-details)        ARGS=(--source steam --kind app_details) ;;
  steam-players)        ARGS=(--source steam --kind player_count) ;;
  steam-reviews)        ARGS=(--source steam --kind review --state-file "$STATE_DIR/steam_reviews.json") ;;
  steam-review-summary) ARGS=(--source steam --kind review_summary) ;;
  danawa)               ARGS=(--source danawa) ;;
  *) echo "알 수 없는 수집 이름: $NAME" >&2; exit 2 ;;
esac

command -v flock >/dev/null || { echo "flock 명령이 없습니다 (dnf install util-linux)" >&2; exit 1; }
exec 9>"$LOCK_DIR/collector-$NAME.lock"
if ! flock -n 9; then
  echo "collector $NAME: 이전 실행이 아직 끝나지 않아 이번 실행은 건너뜀"
  exit 0
fi

cd "$REPO/collector"
echo "collector $NAME: 시작 ($(date -u +%FT%TZ))"
"$PYTHON" -m collector.main "${ARGS[@]}"
echo "collector $NAME: 끝 ($(date -u +%FT%TZ))"
