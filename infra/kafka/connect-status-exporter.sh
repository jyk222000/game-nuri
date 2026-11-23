#!/usr/bin/env bash
# Kafka Connect 커넥터·작업 상태를 node_exporter textfile 지표로 내보낸다 (kafka1에서 1분마다).
# kafka_exporter는 Connect 작업이 FAILED인지 알려 주지 않아서 따로 만든다.
# 출력: /var/lib/node_exporter/textfile/kafka_connect.prom
#   kafka_connect_task_failed{connector="..."}               실패한 작업 수
#   kafka_connect_tasks{connector="...",state="RUNNING"}     상태별 작업 수
#   kafka_connect_connector_running{connector="..."}         커넥터가 RUNNING이면 1
#   kafka_connect_status_last_success_timestamp_seconds      마지막으로 상태를 읽은 시각
set -euo pipefail
URL="${CONNECT_URL:-http://kafka1:8083}"
OUT_DIR="${OUT_DIR:-/var/lib/node_exporter/textfile}"
OUT="$OUT_DIR/kafka_connect.prom"
TMP="$(mktemp "$OUT_DIR/.kafka_connect.XXXXXX")"
trap 'rm -f "$TMP"' EXIT

curl -fsS -m 10 "$URL/connectors?expand=status" | python3 -c '
import json, sys, time
data = json.load(sys.stdin)
print("# HELP kafka_connect_task_failed Number of FAILED tasks per connector")
print("# TYPE kafka_connect_task_failed gauge")
for name, v in sorted(data.items()):
    failed = sum(1 for t in v["status"]["tasks"] if t["state"] == "FAILED")
    print("kafka_connect_task_failed{connector=\"%s\"} %d" % (name, failed))
print("# HELP kafka_connect_tasks Tasks per connector by state")
print("# TYPE kafka_connect_tasks gauge")
for name, v in sorted(data.items()):
    states = {}
    for t in v["status"]["tasks"]:
        states[t["state"]] = states.get(t["state"], 0) + 1
    for st, n in sorted(states.items()):
        print("kafka_connect_tasks{connector=\"%s\",state=\"%s\"} %d" % (name, st, n))
print("# HELP kafka_connect_connector_running 1 if the connector is RUNNING")
print("# TYPE kafka_connect_connector_running gauge")
for name, v in sorted(data.items()):
    print("kafka_connect_connector_running{connector=\"%s\"} %d" % (name, 1 if v["status"]["connector"]["state"] == "RUNNING" else 0))
print("# HELP kafka_connect_status_last_success_timestamp_seconds Last successful status read")
print("# TYPE kafka_connect_status_last_success_timestamp_seconds gauge")
print("kafka_connect_status_last_success_timestamp_seconds %d" % time.time())
' > "$TMP"
chmod 644 "$TMP"
mv "$TMP" "$OUT"
trap - EXIT
