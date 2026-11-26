# 2. ERD · MariaDB 테이블 (mariadb-pr)

테이블 29개를 설계하고 mariadb-pr에서 만듭니다. mariadb-re에는 **복제로** 같은 테이블이 생깁니다.
서버 설치·복제 설정은 `infra/workbook/02-mariadb.md`에 있고, 이 문서는 **테이블 설계와 만드는 순서**입니다. 원본은 `docs/contracts/erd.sql`입니다.

## 2-1. 설계한 테이블 29개
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

가격·게임 테이블은 Kafka Connect만 쓰고, 사용자·알림 테이블 7개는 Backend만 씁니다.

## 2-2. 처음 만들기
```
# 서버가 mariadb-pr 인지 확인 (테이블은 Primary에서만 만든다)
[root@mariadb-pr ~]# hostname

# 시간대가 UTC 인지, 문자셋이 utf8mb4 인지 확인 (팀 규칙: 시간은 UTC)
[root@mariadb-pr ~]# mariadb -u root -p -e "SELECT @@hostname, @@time_zone, @@character_set_server;"

# 스키마 적용. CREATE TABLE 29개가 만들어진다
[root@mariadb-pr ~]# mariadb -h 10.0.2.101 -u gamenuri -p < /opt/game-nuri/repo/docs/contracts/erd.sql

# stores 에 판매처 기본값 8곳 넣기 (INSERT IGNORE 라 여러 번 실행해도 안전)
[root@mariadb-pr ~]# mysql -u root -p gamenuri < /opt/game-nuri/repo/docs/contracts/erd_seed_stores_1123.sql
```
만들어졌는지 확인합니다.
```
[root@mariadb-pr ~]# mariadb -u root -p gamenuri

# 테이블 목록
MariaDB [gamenuri]> SHOW TABLES;

# 테이블 개수. 29 가 나와야 한다
MariaDB [gamenuri]> SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='gamenuri';

# 가격 테이블의 컬럼과 PK 확인 (PK 가 5개 컬럼인지)
MariaDB [gamenuri]> SHOW CREATE TABLE prices_current\G
MariaDB [gamenuri]> EXIT;
```

## 2-3. 설계가 바뀔 때 (이미 만든 서버를 바꾸기)
**순서는 항상 ALTER(테이블) → Connect 설정(`pk.fields`) → refiner입니다.** 컬럼이 없는데 새 필드가 들어오면 JDBC Sink가 멈추기 때문입니다.

| 날짜 | 변경 | 이유 | 파일 |
|---|---|---|---|
| 11/22 | 가격 테이블에 `platform`, `item_condition`, PK 5개 컬럼. `games`에 `aggregated_rating`(·count), `game_platforms`에 `release_date` | 같은 게임의 플랫폼·신품/중고가 덮어쓰지 않게. 평론 점수·플랫폼별 출시일이 분석에 필요 | `erd_alter_1122.sql` |
| 11/23 | `game_review_stats` 추가 (29개째) | Steam 리뷰 수·긍정률을 `review_summaries`와 따로 보관 | `erd_alter_1123.sql` |
| 11/23 | `stores` 기본값 8곳 | 빠져 있던 시드 | `erd_seed_stores_1123.sql` |
| 11/24 | `variant_name` 추가 | 본편 상품이 없는 플랫폼의 에디션 가격 이름 표시(#93) | `erd_alter_1124.sql` |

```
# 1) 가격 테이블이 비어 있는지 확인. 둘 다 0 이어야 한다
#    행이 있으면 새 NOT NULL 칸이 빈 문자열로 채워지므로 실행하지 말고 팀장과 상의
[root@mariadb-pr ~]# mysql -u root -p gamenuri -e "SELECT COUNT(*) FROM prices_current; SELECT COUNT(*) FROM price_history;"

# 2) 둘 다 0 일 때만: platform, item_condition 추가와 PK 변경 (한 번만. DROP PRIMARY KEY 포함, 되돌릴 수 없음)
[root@mariadb-pr ~]# mysql -u root -p gamenuri < /opt/game-nuri/repo/docs/contracts/erd_alter_1122.sql

# 3) Steam 리뷰 수·긍정률 테이블 추가 (이미 있으면 아무 일도 하지 않음)
[root@mariadb-pr ~]# mysql -u root -p gamenuri < /opt/game-nuri/repo/docs/contracts/erd_alter_1123.sql

# 4) 에디션 가격 이름 칸 추가. 정제기를 새 코드로 바꾸기 전에 먼저
[root@mariadb-pr ~]# mysql -u root -p gamenuri < /opt/game-nuri/repo/docs/contracts/erd_alter_1124.sql

# 5) 칸이 생겼는지 확인
[root@mariadb-pr ~]# mysql -u root -p gamenuri -e "SHOW COLUMNS FROM prices_current LIKE 'variant_name';"
```

## 2-4. 복제 확인 (mariadb-re, 읽기만)
```
# 서버 이름 확인 (mariadb-re 여야 한다)
[root@mariadb-re ~]# hostname

# Primary 에서 만든 테이블이 복제됐는지
[root@mariadb-re ~]# mysql -u root -p gamenuri -e "SHOW TABLES;"

# 복제 상태. Slave_IO_Running, Slave_SQL_Running 이 Yes, Seconds_Behind_Master 가 0 근처면 정상
# (안 되면 SHOW SLAVE STATUS\G)
[root@mariadb-re ~]# mysql -u root -p -e "SHOW REPLICA STATUS\G"
```
- Replica에 쓰면 복제가 어긋납니다. `read_only`는 root를 막지 못하므로 읽기 명령만 입력합니다.
- 칸을 추가하는 코드(refiner, Backend)를 배포하기 **전에** DB에 칸을 먼저 추가합니다. 반대 순서면 조회가 오류가 납니다.
