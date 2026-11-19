#!/usr/bin/env bash
# backup 서버에서 cron으로 실행. 7일 보관
set -euo pipefail
source /etc/game-nuri/backup.env     # MARIADB_PASSWORD, MONGO_URI (Git에 없음)
DAY=$(date +%F)
DIR=/backup/$DAY && mkdir -p "$DIR"
mariadb-dump -h mariadb-r -u backup -p"$MARIADB_PASSWORD" --single-transaction gamenuri | gzip > "$DIR/mariadb.sql.gz"
mongodump --uri "$MONGO_URI" --readPreference=secondary --gzip --archive="$DIR/mongo.archive.gz"
find /backup -maxdepth 1 -type d -mtime +7 -exec rm -rf {} +
echo "backup ok $DAY"
