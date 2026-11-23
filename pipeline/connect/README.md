# Kafka Connect 커넥터 설정

토픽을 저장소로 옮기는 Sink 커넥터 설정이다. 코드가 아니라 JSON 설정이고, `apply.sh`로 Connect에 등록한다.
등록은 한 대(`kafka1:8083`)에만 하면 된다. 설정이 Kafka 내부 토픽에 저장돼 Connect 3대가 나눠 맡는다.
서버 구성은 `infra/kafka/README.md`.

| 파일 | 읽는 토픽 | 저장 위치 | 방식 | 등록 조건 |
|---|---|---|---|---|
| `jdbc-sink-prices-current.json` | refined.prices | MariaDB `prices_current` | upsert (game_id, store, edition) | ERD 적용 후 |
| `jdbc-sink-price-history.json` | refined.prices | MariaDB `price_history` | insert | ERD 적용 후 |
| `jdbc-sink-requirements.json` | refined.requirements | MariaDB `game_requirements` | upsert (game_id) | ERD 적용 후 |
| `jdbc-sink-review-summary.json` | refined.review_summary | MariaDB `review_summaries` | upsert (game_id) | ERD 적용 후 |
| `mongo-sink-raw.json` | raw.* | MongoDB `raw_itad`·`raw_danawa`·`raw_steam`·`raw_igdb` (토픽별) | 원본 그대로 + `ingested_at` | MongoDB 계정 |
| `mongo-sink-games.json` | refined.games | MongoDB `games` (→ Monstache → ES) | game_id 기준 교체 | MongoDB 계정 |
| `mongo-sink-reviews.json` | raw.steam | MongoDB `reviews` | 원본 그대로 | 아래 "남은 문제" 확인 후 |
| `es-sink-clickstream.json` | clickstream | ES `clickstream` | 이벤트 저장 | ES 플러그인 설치 후 |

## 등록

kafka1에서 레포 루트(`/opt/game-nuri/repo`)에 `.env`를 만든다(`chmod 600`, 커밋 금지). 필요한 값:

```
KAFKA_CONNECT_URL=http://kafka1:8083
MARIADB_USER=...
MARIADB_PASSWORD=...
MONGO_URI=mongodb://<계정>:<비밀번호>@mongodb-pr:27017,mongo-se1:27017,mongo-se2:27017/gamenuri_raw?replicaSet=rs0&authSource=admin
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
- 시간 형식 — 정제 규칙표 R04대로 `refined.*`의 시간은 UTC `YYYY-MM-DD HH:MM:SS` 문자열로 온다. MariaDB가 이 형식을 `DATETIME`으로 그대로 받으므로 변환 설정을 두지 않는다. `2026-11-19T02:30:00Z`처럼 `T`·`Z`가 붙은 형식이 오면 적재가 실패한다.
- `topic.override.<토픽>.collection` — 원본은 출처별 컬렉션에 나눠 담는다(MongoDB 구축 문서 4장 안). 목록에 없는 토픽이 오면 `raw_unknown`에 들어간다.
- `ingested_at` (InsertField) — 저장 시각을 BSON Date로 넣는다. 원본의 `collected_at`은 문자열이라 TTL 인덱스가 동작하지 않기 때문이다. TTL을 쓸지는 컬렉션 확정 때 정한다.
- `max.num.retries=3`, `retries.defer.timeout=5000` — MongoDB PRIMARY가 바뀌는 몇 초 동안의 쓰기 오류를 재시도로 넘긴다.
- `auto.create: false` — 테이블은 ERD(`docs/contracts/erd.sql`)로만 만든다.
- `value.converter.schemas.enable: true` — JDBC Sink는 컬럼 타입을 알아야 해서 `refined.*`는 JSON+schema 형식이다(`docs/contracts/messages/`).

## 남은 문제

- `refined.games` → MariaDB `games`, `game_store_ids` 커넥터가 없다. `docs/contracts/messages/`에 `refined.games` 형식이 정해진 뒤 만든다. `game_store_ids`처럼 메시지 하나가 여러 행이 되는 테이블은 별도 토픽이나 다른 방법이 필요하다.
- `mongo-sink-reviews`는 `raw.steam` 전체(사양·동접자·보유 게임 포함)를 `reviews`에 넣는다. 리뷰만 남기는 방법(정제에서 리뷰 전용 토픽으로 펼치기 등)을 정해야 한다.
- 장애·재시작 뒤에는 마지막 기록 위치부터 다시 읽어 몇 건이 중복될 수 있다. upsert 테이블은 결과가 같지만 `price_history`(insert)는 같은 행이 생길 수 있다.
