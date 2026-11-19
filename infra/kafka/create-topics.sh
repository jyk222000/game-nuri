#!/usr/bin/env bash
# kafka1에서 실행. docs/contracts/topics.md 와 일치
set -euo pipefail
BS=kafka1:9092,kafka2:9092,kafka3:9092
create() { kafka-topics.sh --bootstrap-server $BS --create --if-not-exists --topic "$1" --partitions 3 --replication-factor 3 --config retention.ms="$2"; }
D=86400000
for t in raw.price raw.console raw.steam raw.igdb; do create $t $((7*D)); done
for t in refined.games refined.prices refined.unmatched clickstream; do create $t $((3*D)); done
kafka-topics.sh --bootstrap-server $BS --list
