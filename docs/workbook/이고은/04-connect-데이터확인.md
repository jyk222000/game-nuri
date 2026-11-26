# 4. Kafka Connect 설정 적용과 데이터 확인

## 4-1. Connect 설정 적용
`refined.*`를 MariaDB에, `raw.*`를 MongoDB에 옮기는 Sink 설정(`pipeline/connect/*.json`)을 Connect에 등록합니다.
코드가 아니라 JSON 설정이고 `apply.sh`로 등록합니다. **한 대(kafka1:8083)에만** 등록하면 설정이 Kafka 내부 토픽에 저장되어 3대가 나눠 맡습니다.

| 파일 | 읽는 토픽 | 저장 위치 / 방식 |
|---|---|---|
| `jdbc-sink-games.json` | refined.games | games / upsert (game_id) |
| `jdbc-sink-prices-current.json` | refined.prices | prices_current / upsert (5개 키). `erd_alter_1122.sql` 적용 후 |
| `jdbc-sink-price-history.json` | refined.price_history | price_history / insert (가격이 바뀐 때만) |
| `jdbc-sink-review-stats.json` | refined.review_stats | game_review_stats / upsert. `erd_alter_1123.sql` 적용 후 |
| `jdbc-sink-game-links.json` | refined.game_genres 등 4개 | 연결 테이블 / upsert (모든 컬럼이 키) |
| `mongo-sink-raw.json` | raw.* | MongoDB raw_* 컬렉션. 리뷰(kind=review)는 제외 (#127) |
| `mongo-sink-unmatched.json` | refined.unmatched | MongoDB unmatched |

kafka1의 레포 루트에 `.env`가 있어야 합니다(chmod 600, 커밋 금지). 필요한 값의 이름: `KAFKA_CONNECT_URL`, `MARIADB_USER`, `MARIADB_PASSWORD`, `MONGO_URI`, `ES_USER`, `ES_PASSWORD`.
```
# 최신 설정 파일 받기 (sudo 없이)
[adminc@kafka1 ~]$ cd /opt/game-nuri/repo && git pull

# 커넥터 설정 폴더로 이동
[adminc@kafka1 repo]$ cd pipeline/connect

# envsubst 가 없다는 오류가 나면 한 번만 설치
[adminc@kafka1 connect]$ sudo dnf install -y gettext

# 바뀐 커넥터만 골라서 등록 (이미 있으면 설정을 덮어쓴다). 이름은 파일 이름에서 .json 을 뺀 것
[adminc@kafka1 connect]$ ./apply.sh mongo-sink-raw
[adminc@kafka1 connect]$ ./apply.sh jdbc-sink-prices-current jdbc-sink-price-history

# 이름을 안 쓰면 이 폴더의 커넥터를 전부 등록한다
[adminc@kafka1 connect]$ ./apply.sh

# 등록된 커넥터 목록
[adminc@kafka1 connect]$ curl -s http://kafka1:8083/connectors

# 커넥터 하나의 상태. RUNNING 이면 정상, FAILED 면 trace 에 원인이 나온다
[adminc@kafka1 connect]$ curl -s http://kafka1:8083/connectors/mongo-sink-raw/status
```

### 설정 값의 이유
- `dialect.name: MySqlDatabaseDialect`: JDBC 커넥터는 `jdbc:mariadb://` 주소로 DB 종류를 알아내지 못한다. 지정하지 않으면 upsert가 동작하지 않는다.
- `auto.create: false`: 테이블은 `erd.sql`로만 만든다. 커넥터가 마음대로 테이블을 만들지 못하게 한다.
- `value.converter.schemas.enable: true`: JDBC Sink는 컬럼 타입을 알아야 해서 `refined.*`는 JSON+schema 형식으로 보낸다.
- 시간 형식: TimestampConverter 패턴은 `yyyy-MM-dd'T'HH:mm:ss`이고 끝에 `X`를 붙이지 않는다. 소수 초가 붙은 UTC 값도 받기 위해서다.
- 커넥터의 `pk.fields`는 메시지 형식의 키와 같아야 하고, `pipeline/tests/test_connect_configs.py`가 확인한다.

## 4-2. 단계별 데이터 확인 (읽기만)
데이터가 단계마다 잘 들어갔는지 보고, 문제가 있으면 **어느 단계에서 막혔는지** 찾습니다.
```
# 1) 정제: refiner 로그에 오류가 없는지 (최근 50줄)
[adminc@kafka1 ~]$ sudo journalctl -u refiner -n 50 --no-pager

# 2) 적재: 커넥터가 RUNNING 인지
[adminc@kafka1 ~]$ curl -s http://kafka1:8083/connectors/jdbc-sink-prices-current/status

# 3) 저장: 주요 테이블 행 수
[root@mariadb-pr ~]# mysql -u root -p gamenuri -e "SELECT COUNT(*) FROM games; SELECT COUNT(*) FROM prices_current; SELECT COUNT(*) FROM price_history;"

# 4) 저장: 다나와 신품·중고별로 정가와 할인율이 채워졌는지
[root@mariadb-pr ~]# mysql -u root -p gamenuri -e "SELECT item_condition, COUNT(*), SUM(regular_krw IS NOT NULL), SUM(discount_pct>0) FROM prices_current WHERE store='danawa' GROUP BY item_condition;"

# 5) 저장: 에디션 가격(variant_name)이 들어갔는지 5개만
[root@mariadb-pr ~]# mysql -u root -p gamenuri -e "SELECT game_id, store, platform, variant_name, price_krw FROM prices_current WHERE variant_name IS NOT NULL LIMIT 5;"

# 6) 복제: Replica 가 따라오고 있는지
[root@mariadb-re ~]# mysql -u root -p -e "SHOW REPLICA STATUS\G"
```
| 단계 | 어디서 | 무엇을 | 정상 기준 |
|---|---|---|---|
| 정제 | kafka1 | `journalctl -u refiner` | 오류 없음, unmatched는 일부만 |
| 적재 | kafka1 | Connect 상태 | RUNNING (FAILED 없음) |
| 저장 | mariadb-pr | 테이블 행 수, 컬럼 값 | 기대한 컬럼이 채워짐 |
| 복제 | mariadb-re | `SHOW REPLICA STATUS` | IO·SQL 모두 Yes |

## 4-3. 지킬 것
- 테이블 변경 순서: ALTER → Connect 설정 → refiner. 반대로 하면 JDBC Sink가 멈춘다.
- 테이블은 `docs/contracts/erd.sql`로만 만들고, 바꿀 때는 contracts PR로 올린다. 몰래 필드 이름을 바꾸지 않는다.
- Replica(mariadb-re)에는 쓰지 않는다. DROP·TRUNCATE·토픽 삭제는 팀장 확인 후에만 한다.
