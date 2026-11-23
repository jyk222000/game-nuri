#!/usr/bin/env bash
# backup 서버에서 cron으로 실행. 7일 보관
# 설정: /etc/game-nuri/backup.env (Git에 없음)
#   MARIADB_PASSWORD, MONGO_URI        (필수)
#   BACKUP_ROOT                        (선택, 기본 /BACKUP — 별도 디스크 sda3 마운트 지점)
set -euo pipefail
source /etc/game-nuri/backup.env

BACKUP_ROOT="${BACKUP_ROOT:-/BACKUP}"
RETENTION_DAYS=7

# 백업 디스크가 마운트돼 있지 않으면 루트 디스크(/)에 쌓이므로 중단한다. 루트 폴더는 만들지 않는다.
if [[ -z "$BACKUP_ROOT" || "$BACKUP_ROOT" == "/" || ! -d "$BACKUP_ROOT" ]]; then
  echo "backup FAILED: 백업 폴더가 없다 ($BACKUP_ROOT). 디스크 마운트를 확인하세요." >&2
  exit 1
fi

DAY=$(date +%F)
DIR="$BACKUP_ROOT/$DAY"
mkdir -p "$DIR"

# MariaDB 비밀번호가 명령줄(ps)에 보이지 않게 임시 옵션 파일로 넘긴다 (끝나면 지운다).
umask 077
MYCNF=$(mktemp)
trap 'rm -f "$MYCNF"' EXIT
printf '[client]\nuser=backup\npassword=%s\n' "$MARIADB_PASSWORD" > "$MYCNF"

# 쓰는 도중 실패해도 반쪽짜리 파일이 정상 백업처럼 남지 않게 .tmp로 쓰고 끝나면 이름을 바꾼다.
mariadb-dump --defaults-extra-file="$MYCNF" -h mariadb-re --single-transaction gamenuri \
  | gzip > "$DIR/mariadb.sql.gz.tmp"
mv "$DIR/mariadb.sql.gz.tmp" "$DIR/mariadb.sql.gz"

# 참고: mongodump의 --uri는 계정 정보가 명령줄에 보인다(백업 서버는 팀 계정만 접속).
mongodump --uri "$MONGO_URI" --readPreference=secondary --gzip --archive="$DIR/mongo.archive.gz.tmp"
mv "$DIR/mongo.archive.gz.tmp" "$DIR/mongo.archive.gz"

# 7일 지난 날짜 폴더(YYYY-MM-DD)만 지운다. 그 밖의 폴더·파일은 건드리지 않는다.
find "$BACKUP_ROOT" -mindepth 1 -maxdepth 1 -type d -name '20??-??-??' \
  -mtime +"$RETENTION_DAYS" -exec rm -rf -- {} +

echo "backup ok $DAY"
