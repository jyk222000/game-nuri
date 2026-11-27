# 9. ERD · MariaDB 테이블 (mariadb-pr)

테이블 29개를 mariadb-pr에서 만듭니다. mariadb-re에는 **복제로** 같은 테이블이 생깁니다. 원본은 `docs/contracts/erd.sql`입니다.

## 9-1. 설계한 테이블 29개
| 분류 | 테이블 | 설명 |
|---|---|---|
| 게임 | `games` | 게임 기본 정보(IGDB). 평론 점수 `aggregated_rating` 포함 |
| | `game_aliases` | 한글 이름·줄임말·다나와 상품명. 상품명을 게임에 연결할 때 사용 |
| | `game_store_ids` | 스토어별 외부 ID(Steam appid, ITAD id, 다나와 pcode)와 게임 연결 |
| | `game_time_to_beat` | 클리어 시간(IGDB) |
| | `game_requirements` | PC 최소·권장 사양 텍스트(Steam) |
| | `game_review_stats` | Steam 스토어 리뷰 수·긍정률(한국어/전체) |
| | `review_summaries` | AI 리뷰 요약(하루 1회 배치) |
| | `player_counts` | 동시 접속자 수 |
| 분류·연결 | `platforms`, `genres`, `companies`, `tags` | 마스터 |
| | `game_platforms`, `game_genres`, `game_companies`, `game_tags` | 게임과 마스터를 잇는 연결 테이블 (플랫폼별 출시일 포함) |
| | `game_series`, `game_series_map` | 시리즈와 게임의 연결 |
| 가격 | `stores` | 판매처 8곳 |
| | `prices_current` | 현재 가격. PK = (game_id, store, edition, platform, item_condition) |
| | `price_history` | 가격 변화 이력 |
| | `exchange_rates` | 원화 환산에 쓴 환율 |
| 사용자·알림 | `users`, `user_specs`, `user_owned_games` | 사용자, 사용자 PC 사양, 보유 게임 |
| | `wishlists`, `notification_settings`, `alerts`, `alert_logs` | 찜, 알림 설정, 목표가 알림, 발송 기록 |

> <- 가격·게임 테이블은 Kafka Connect만 쓰고, 사용자·알림 테이블 7개는 Backend만 씁니다.

## 9-2. 테이블 만들기
```
# 지금 서버가 mariadb-pr 이 맞는지 확인. 테이블은 Primary 에서만 만든다
[adminc@mariadb-pr ~]$ hostname

# 시간대가 UTC 인지, 문자셋이 utf8mb4 인지 확인한다. 팀 규칙: 시간은 항상 UTC
[adminc@mariadb-pr ~]$ sudo mariadb -e "SELECT @@hostname, @@time_zone, @@character_set_server;"

# 스키마 파일을 적용한다. CREATE TABLE 29개가 만들어진다. 비밀번호는 입력창에서 직접 친다
[adminc@mariadb-pr ~]$ mariadb -h 10.0.2.101 -u gamenuri -p < /opt/game-nuri/repo/docs/contracts/erd.sql

# stores 에 판매처 기본값 8곳을 넣는다. INSERT IGNORE 라 여러 번 실행해도 안전하다
[adminc@mariadb-pr ~]$ sudo mariadb gamenuri < /opt/game-nuri/repo/docs/contracts/erd_seed_stores_1123.sql
```

## 9-3. 만들어졌는지 확인
```
# 테이블 개수를 센다. 29 가 나와야 한다
[adminc@mariadb-pr ~]$ sudo mariadb gamenuri -e "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='gamenuri';"

# 가격 테이블의 PK 가 5개 컬럼(game_id, store, edition, platform, item_condition)인지 확인한다
[adminc@mariadb-pr ~]$ sudo mariadb gamenuri -e "SHOW CREATE TABLE prices_current\G"
```

## 9-4. 복제 확인 (mariadb-re, 읽기만)
```
# 서버 이름 확인. mariadb-re 여야 한다. 이 서버에서는 SELECT·SHOW 만 입력한다
[adminc@mariadb-re ~]$ hostname

# Primary 에서 만든 테이블이 복제로 생겼는지 확인한다
[adminc@mariadb-re ~]$ sudo mariadb gamenuri -e "SHOW TABLES;"

# 복제 상태를 확인한다. Slave_IO_Running, Slave_SQL_Running 이 모두 Yes 면 정상이다
# 명령이 안 되면 SHOW SLAVE STATUS\G 로 입력한다
[adminc@mariadb-re ~]$ sudo mariadb -e "SHOW REPLICA STATUS\G"
```
