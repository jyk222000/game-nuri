#!/usr/bin/env bash
# kafka1에서 실행. docs/contracts/topics.md 와 일치
# min.insync.replicas는 브로커 기본값(2)을 따른다. 토픽에 따로 넣지 않는다:
# 2대 장애 때 브로커 기본값만 바꿔 1대 운영으로 전환하는 절차(README 6장)가 토픽 설정에 막히지 않게 하려는 것이다.
set -euo pipefail
BS=kafka1:9092,kafka2:9092,kafka3:9092
create() { kafka-topics.sh --bootstrap-server $BS --create --if-not-exists --topic "$1" --partitions 3 --replication-factor 3 --config retention.ms="$2"; }
D=86400000
for t in raw.price raw.console raw.steam raw.igdb; do create $t $((7*D)); done
for t in refined.games refined.prices refined.price_history refined.requirements refined.review_summary refined.unmatched clickstream; do create $t $((3*D)); done
# 한 게임이 여러 행이 되는 테이블용 14개 (docs/contracts/messages/refined.links.json)
for t in refined.game_store_ids refined.time_to_beat refined.player_counts \
         refined.genres refined.companies refined.tags refined.game_series \
         refined.game_aliases refined.exchange_rates refined.game_genres refined.game_platforms \
         refined.game_companies refined.game_tags refined.game_series_map; do create $t $((3*D)); done
kafka-topics.sh --bootstrap-server $BS --list
