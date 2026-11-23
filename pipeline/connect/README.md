# Kafka Connect 커넥터 설정

토픽을 저장소로 옮기는 Sink 커넥터 설정이다. 코드가 아니라 JSON 설정이고, `apply.sh`로 Connect에 등록한다.
등록은 한 대(`kafka1:8083`)에만 하면 된다. 설정이 Kafka 내부 토픽에 저장돼 Connect 3대가 나눠 맡는다.
서버 구성은 `infra/kafka/README.md`.

토픽별 테이블·키·필드는 `docs/contracts/topics.md`와 `messages/` (한 게임이 여러 행이 되는 14개는 `messages/refined.links.json`). 커넥터의 `pk.fields`는 메시지 형식의 키와 같아야 하고, `pipeline/tests/test_connect_configs.py`가 확인한다.

| 파일 | 읽는 토픽 | 저장 위치 | 방식 | 등록 조건 |
|---|---|---|---|---|
| `jdbc-sink-games.json` | refined.games | `games` | upsert (game_id) | 바로 |
| `jdbc-sink-game-store-ids.json` | refined.game_store_ids | `game_store_ids` | upsert | 바로 |
| `jdbc-sink-time-to-beat.json` | refined.time_to_beat | `game_time_to_beat` | upsert | 바로 |
| `jdbc-sink-requirements.json` | refined.requirements | `game_requirements` | upsert | 바로 (시간 변환 추가) |
| `jdbc-sink-player-counts.json` | refined.player_counts | `player_counts` | upsert | 바로 |
| `jdbc-sink-review-summary.json` | refined.review_summary | `review_summaries` | upsert | 바로 (시간 변환 추가) |
| `jdbc-sink-prices-current.json` | refined.prices | `prices_current` | upsert (game_id, store, edition, platform, item_condition) | `erd_alter_1122.sql` 적용 후 |
| `jdbc-sink-price-history.json` | refined.prices, refined.price_history | `price_history` | upsert (유니크 키 game_id, store, edition, platform, item_condition, collected_at) | `erd_alter_1123.sql`(#48) 적용 후 |
| `jdbc-sink-game-platforms.json` | refined.game_platforms | `game_platforms` | upsert (game_id, platform) | 바로 |
| `jdbc-sink-genres.json` · `companies` · `tags` · `game-series` · `game-aliases` · `exchange-rates` | 같은 이름의 refined.* | 같은 이름의 테이블 | upsert | 바로 |
| `jdbc-sink-game-links.json` | refined.game_genres·game_companies·game_tags·game_series_map | 토픽 이름에서 `refined.`를 뗀 테이블 | upsert (모든 컬럼이 키) | 바로 |
| `mongo-sink-raw.json` | raw.* | MongoDB `raw_itad`·`raw_danawa`·`raw_steam`·`raw_igdb` (토픽별) | 원본 그대로 + `ingested_at` | 등록됨 |
| `mongo-sink-games.json` | refined.games | MongoDB `games` (→ Monstache → ES) | game_id 기준 교체 | 등록됨 |
| `mongo-sink-unmatched.json` | refined.unmatched | MongoDB `unmatched` | 그대로 + `ingested_at` | 바로 |
| `mongo-sink-reviews.json` | raw.steam | MongoDB `reviews` | 원본 그대로 | 아래 "남은 문제" 확인 후 |
| `es-sink-clickstream.json` | clickstream | ES `clickstream-YYYY.MM.dd` (날짜별) | 이벤트 저장 (문서 ID = 토픽+파티션+오프셋이라 중복 없음) | ES 설치·계정 후. 플러그인: Confluent Elasticsearch Sink 16.0.1 (ES 8.x·9.x) |

가격 테이블 변경: `docs/contracts/erd_alter_1122.sql` (이고은).

## 등록

kafka1에서 레포 루트(`/opt/game-nuri/repo`)에 `.env`를 만든다(`chmod 600`, 커밋 금지). 필요한 값:

```
KAFKA_CONNECT_URL=http://kafka1:8083
MARIADB_USER=...
MARIADB_PASSWORD=...
MONGO_URI=mongodb://<계정>:<비밀번호>@mongodb-pr:27017,mongo-se1:27017,mongo-se2:27017/gamenuri_raw?replicaSet=rs0&authSource=admin
ES_USER=...        # es-sink-clickstream용 (ES 보안을 켠 경우)
ES_PASSWORD=...
```

```bash
cd /opt/game-nuri/repo/pipeline/connect
./apply.sh jdbc-sink-prices-current jdbc-sink-price-history   # 준비된 것만 골라서
./apply.sh                                                    # 전부
curl -s http://kafka1:8083/connectors/<이름>/status          # 상태 (FAILED면 trace에 원인)
```

`envsubst`가 없으면 `sudo dnf install -y gettext`.

## 설정 값의 이유

- `dialect.name: MySqlDatabaseDialect` — JDBC 커넥터는 `jdbc:mariadb://` 주소로 DB 종류를 알아내지 못한다. 지정하지 않으면 upsert가 동작하지 않는다.
- 시간 형식 — `refined.*`의 DATETIME 값은 UTC `2026-11-19T02:30:00Z` 문자열로 온다(refiner README). `TimestampConverter`(`transforms.ts`)가 DATETIME으로 바꿔 넣는다. 한 커넥터에 시간 필드가 하나씩이라 변환도 하나씩이다.
- `jdbc-sink-game-links` — 연결 테이블 네 개는 모든 컬럼이 기본 키라 설정이 같다. `RegexRouter`로 토픽 이름(`refined.game_genres`)을 테이블 이름(`game_genres`)으로 바꾸고, `pk.fields`를 비워 모든 필드를 키로 쓴다.
- `topic.override.<토픽>.collection` — 원본은 출처별 컬렉션에 나눠 담는다(MongoDB 구축 문서 4장 안). 목록에 없는 토픽이 오면 `raw_unknown`에 들어간다.
- `ingested_at` (InsertField) — 저장 시각을 BSON Date로 넣는다. 원본의 `collected_at`은 문자열이라 TTL 인덱스가 동작하지 않기 때문이다. TTL을 쓸지는 컬렉션 확정 때 정한다.
- `max.num.retries=3`, `retries.defer.timeout=5000` — MongoDB PRIMARY가 바뀌는 몇 초 동안의 쓰기 오류를 재시도로 넘긴다.
- `auto.create: false` — 테이블은 ERD(`docs/contracts/erd.sql`)로만 만든다.
- `value.converter.schemas.enable: true` — JDBC Sink는 컬럼 타입을 알아야 해서 `refined.*`는 JSON+schema 형식이다(`docs/contracts/messages/`).

## 남은 문제

- `mongo-sink-reviews`는 `raw.steam` 전체(사양·동접자·보유 게임 포함)를 `reviews`에 넣는다. 리뷰만 남기는 방법(정제에서 리뷰 전용 토픽으로 펼치기 등)을 정해야 한다.
- 연결 테이블은 행을 지우지 않는다. 원본에서 빠진 장르·태그 등은 옛 행이 남는다.
- `price_history`는 유니크 키 + upsert라 같은 메시지를 다시 받아도 한 줄만 남는다. 테이블 PK는 자동 번호 `id`이지만 MariaDB의 `ON DUPLICATE KEY UPDATE`가 유니크 키에도 걸린다.
