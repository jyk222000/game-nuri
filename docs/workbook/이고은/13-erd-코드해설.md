# 13. ERD 코드 해설 (docs/contracts/erd.sql)

9번 문서가 "테이블 29개와 만드는 명령"이었다면, 이 문서는 **SQL을 줄마다 풀어서** 설명합니다.
SQL 주석은 `--`로 씁니다(레포의 `erd.sql`과 같은 방식). 코드는 `erd.sql`에서 핵심 테이블만 뽑았고, 주석은 설명용으로 더 붙였습니다.

## 13-1. 스키마 파일의 규칙
```sql
-- 모든 테이블에 PRIMARY KEY 가 있다 (Connect 가 upsert 할 때 키가 필요하다)
-- Kafka Connect 가 쓰는 테이블의 컬럼 이름 = docs/contracts/messages 의 필드 이름 (snake_case)
--   → JDBC Sink 는 메시지 필드를 전부 컬럼에 넣으므로, 컬럼이 하나라도 없으면 적재가 멈춘다
-- Kafka Connect 가 쓰는 테이블에는 FK·CHECK 를 걸지 않는다
--   → 토픽 도착 순서가 보장되지 않는다. 가격이 게임보다 먼저 와도 제약에 걸려 Sink 가 멈추면 안 된다
-- 문자셋·엔진은 DB 기본값(utf8mb4, InnoDB)을 따른다 (테이블마다 적지 않는다)

-- 데이터베이스를 만든다. 이미 있으면 건너뛴다. 한글·이모지가 들어가므로 utf8mb4
CREATE DATABASE IF NOT EXISTS gamenuri DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE gamenuri;
```
> <- FK를 일부러 뺀 것이 가장 큰 설계 결정입니다. 대신 `game_id`가 `games`에 있는지는 조회할 때 JOIN으로 확인합니다.
> 사용자·알림 테이블(Backend가 쓰는 것)에는 FK가 있습니다(`user_owned_games`의 `fk_owned_user` 등).

## 13-2. games : 기준 키 = IGDB ID
```sql
CREATE TABLE games (
  game_id          BIGINT PRIMARY KEY,            -- IGDB ID. 모든 테이블이 이 번호로 게임을 가리킨다(기준 키)
  name             VARCHAR(255) NOT NULL,         -- 영문 이름
  name_ko          VARCHAR(255),                  -- 한글 이름. 없는 게임도 있어서 NULL 허용
  slug             VARCHAR(255),                  -- URL 에 쓰는 이름 (elden-ring)
  summary          TEXT,                          -- 게임 소개(길어서 TEXT)
  release_date     DATE,                          -- 출시일. IGDB 는 유닉스 초로 주므로 정제 때 YYYY-MM-DD 로 바꾼다
  game_type        SMALLINT,                      -- IGDB 종류 코드 (0 = 본편, 그 외 DLC·에디션 …)
  parent_game_id   BIGINT,                        -- DLC·확장이면 본편의 game_id
  version_parent_id BIGINT,                       -- 에디션이면 원본의 game_id
  cover_image_id   VARCHAR(64),                   -- 커버 이미지 코드. 주소(cover_url)는 이 코드로 조합한다
  cover_url        VARCHAR(512),
  rating           DECIMAL(5,2),                  -- IGDB 종합 평점(0~100). 소수 둘째 자리까지
  rating_count     INT,
  aggregated_rating DECIMAL(5,2),                 -- 평론가 평점. 분석 A3(평론 vs 유저)에 쓴다
  aggregated_rating_count INT,
  age_rating       SMALLINT,                      -- ↓ 이 3개는 Steam 에서 온다(refined.games_steam, update)
  korean_supported BOOLEAN,                       --   IGDB 메시지에는 없어서 games 를 만든 메시지와 따로 채운다
  is_online        BOOLEAN,
  updated_at       DATETIME NOT NULL,             -- 시각은 항상 UTC
  INDEX idx_games_name (name),                    -- 이름 검색용
  INDEX idx_games_parent (parent_game_id)         -- "이 본편의 DLC 목록" 조회용
);
```
> <- IGDB 메시지(`refined.games`)에는 `age_rating` 등 Steam 컬럼을 **일부러 넣지 않습니다.** 넣으면 upsert할 때 NULL로 덮어쓰기 때문입니다.
> <- 대신 Steam 메시지가 따로 와서 그 3개 컬럼만 update합니다. 단, Steam 메시지가 게임 줄보다 먼저 오면 update할 줄이 없으므로, 정제 프로그램이 게임 줄이 올 때 한 번 더 보냅니다(`router.py`의 `games_steam`).

## 13-3. game_store_ids : 게임 ID 통합의 핵심
```sql
CREATE TABLE game_store_ids (
  game_id      BIGINT NOT NULL,                   -- IGDB ID (기준)
  store        VARCHAR(32) NOT NULL,              -- steam | itad | danawa
  external_id  VARCHAR(128) NOT NULL,             -- Steam appid, ITAD id(uuid), 다나와 pcode
  PRIMARY KEY (store, external_id),               -- 외부 번호 하나는 게임 하나에만 붙는다
  INDEX idx_game (game_id)                        -- 게임 → 외부 번호 방향 조회용
);
```
> <- PK를 `(game_id, store)`가 아니라 **`(store, external_id)`**로 한 이유: 같은 Steam appid가 서로 다른 게임 둘에 붙는 실수를 DB가 막아 줍니다.
> 한 게임에 스토어 번호가 여러 개(예: 다나와 상품 둘)인 것은 허용합니다.

## 13-4. prices_current : 현재 가격 (upsert)
```sql
CREATE TABLE prices_current (
  game_id          BIGINT NOT NULL,
  store            VARCHAR(32) NOT NULL,          -- steam, epic, gog … 다나와
  edition          VARCHAR(16) NOT NULL,          -- digital | physical | code
  platform         VARCHAR(16) NOT NULL,          -- PC, PS4, PS5, Switch …
  item_condition   VARCHAR(8) NOT NULL,           -- new | used  (condition 은 MariaDB 예약어라 item_condition)
  price_krw        INT NOT NULL,                  -- 원화 환산 금액. 금액은 원화 정수로 저장한다(팀 규칙)
  regular_krw      INT,                           -- 정가(원화)
  discount_pct     INT,                           -- 할인율 %
  price_original   DOUBLE,                        -- 환산 전 금액 (원래 통화 그대로)
  currency_original VARCHAR(8),                   -- 환산 전 통화: KRW | USD | EUR | GBP
  url              VARCHAR(512),
  variant_name     VARCHAR(64),                   -- 에디션 가격이면 에디션 이름, 본편이면 NULL
  collected_at     DATETIME NOT NULL,             -- 수집 시각(UTC)
  PRIMARY KEY (game_id, store, edition, platform, item_condition)   -- 이 5개가 같으면 같은 가격 줄
);
```
> <- PK를 5개로 늘린 이유: 처음에는 `(game_id, store, edition)`이었는데, 같은 게임의 PS4·PS5, 신품·중고가 서로 **덮어쓰는** 문제가 있어서 `platform`, `item_condition`을 추가했습니다(11/22).
> <- Kafka 메시지 키도 같은 5개를 `:`로 이은 값입니다. 같은 키의 메시지는 같은 파티션으로 가서 **순서가 지켜집니다.**
> <- JDBC Sink 설정은 `pk.fields = game_id,store,edition,platform,item_condition`, `insert.mode = upsert`입니다(`pipeline/connect/jdbc-sink-prices-current.json`).

## 13-5. price_history : 가격 변동 이력 (insert)
```sql
CREATE TABLE price_history (
  id               BIGINT AUTO_INCREMENT PRIMARY KEY,   -- 이력은 같은 키가 여러 번 쌓이므로 일련번호를 PK 로 쓴다
  game_id          BIGINT NOT NULL,
  store            VARCHAR(32) NOT NULL,
  edition          VARCHAR(16) NOT NULL,
  platform         VARCHAR(16) NOT NULL,
  item_condition   VARCHAR(8) NOT NULL,
  price_krw        INT NOT NULL,
  regular_krw      INT,
  discount_pct     INT,
  price_original   DOUBLE,                        -- ↓ 이 3개가 빠져 있어서 Sink 가 실패한 적이 있다
  currency_original VARCHAR(8),                   --   JDBC Sink insert 는 메시지의 모든 필드를 컬럼에 넣는다
  url              VARCHAR(512),
  variant_name     VARCHAR(64),
  collected_at     DATETIME NOT NULL,             -- 수집 시각이 아니라 "가격이 바뀐 시각"
  INDEX idx_game_time (game_id, collected_at),                                  -- 게임별 시간순 조회
  INDEX idx_game_platform_time (game_id, platform, item_condition, collected_at)  -- 플랫폼·신품/중고별 그래프
);
```
> <- 이력은 정제 프로그램이 **가격이 바뀐 때만** 보냅니다(`price_change.py`). 그래서 행이 무한정 불어나지 않습니다.
> <- 서버를 재시작하면 같은 메시지가 두 번 들어갈 수 있어(at-least-once) 줄이 겹칠 수 있습니다. Backend가 조회할 때 키 6개로 합칩니다(`backend/app/services/history.py`).

## 13-6. game_aliases, stores
```sql
CREATE TABLE game_aliases (
  alias_id   BIGINT AUTO_INCREMENT PRIMARY KEY,
  game_id    BIGINT NOT NULL,
  alias      VARCHAR(255) NOT NULL,               -- 별칭 (레데리2, 바이오하자드 RE:4 …)
  source     VARCHAR(16) NOT NULL,                -- igdb | llm | manual
  reviewed   BOOLEAN NOT NULL DEFAULT FALSE,      -- 사람이 검수했는지. llm 이 만든 별칭은 검수 전에는 검색·매칭에 쓰지 않는다
  UNIQUE KEY uq_game_alias (game_id, alias),      -- 같은 게임에 같은 별칭 두 번 금지
  INDEX idx_alias (alias)                         -- 상품명 → 게임 찾기용
);

CREATE TABLE stores (                             -- 판매처 기준표 (8곳)
  store         VARCHAR(32) PRIMARY KEY,          -- steam, epic, gog, msstore, blizzard, ea, ubisoft, danawa
  display_name  VARCHAR(64) NOT NULL,
  platform      ENUM('pc','console') NOT NULL,    -- PC 스토어인지 콘솔(다나와)인지
  itad_shop_id  INT UNIQUE                        -- ITAD 판매처 번호(Steam=61). 다나와는 NULL
);
```

## 13-7. 이미 만든 서버에는 어떻게 바꾸나
`erd.sql`은 **처음 만들 때** 쓰는 파일입니다. 이미 테이블이 있는 서버에 같은 파일을 다시 넣으면 `table already exists` 오류가 납니다. 바뀐 부분만 담은 파일을 따로 둡니다(`docs/contracts/`).
| 파일 | 바뀐 내용 | 실행 전 조건 |
|---|---|---|
| `erd_alter_1122.sql` | `prices_current`·`price_history`에 `platform`, `item_condition` 추가(`prices_current`는 PK를 5개로 교체), `games`에 `aggregated_rating`·`aggregated_rating_count`, `game_platforms`에 `release_date` | **가격 테이블 두 개가 비어 있어야 한다.** 행이 있으면 새 NOT NULL 컬럼이 빈 문자열로 채워지므로 실행하지 않고 팀장과 상의 |
| `erd_alter_1123.sql` | `game_review_stats` 새로 만들기 (`CREATE TABLE IF NOT EXISTS`, 기존 데이터는 건드리지 않음) | 없음 |
| `erd_seed_stores_1123.sql` | `stores` 기본값 8곳 (`INSERT IGNORE`라 여러 번 실행해도 안전) | `stores`가 비어 있을 때 |
| `erd_alter_1124.sql` | 가격 테이블 2개에 `variant_name` (`ADD COLUMN IF NOT EXISTS`) | **새 refiner 코드를 올리기 전에** 실행. 컬럼이 없는데 `variant_name`이 오면 JDBC Sink가 멈춘다 |

> <- 모두 **mariadb-pr(Primary)에서만** 실행합니다. mariadb-re(Replica)에는 복제로 반영됩니다. 파일 머리말 예시는 `mysql -u root -p gamenuri < 파일.sql`입니다(비밀번호는 입력창에서 직접 칩니다).
> <- **변경 순서가 중요합니다.** 컬럼을 바꾸는 변경은 ① DB `ALTER` → ② Connect 설정(`pk.fields` 등, 남현식) → ③ refiner 배포 순서입니다. 순서가 바뀌면 메시지는 새 필드를 보내는데 테이블에 컬럼이 없어 Sink가 멈춥니다.
> <- 같은 이유로 `erd.sql`을 바꿀 때는 **계약 PR**로 따로 올리고, 영향받는 파트(정제·Connect·Backend)를 PR 본문에 적습니다.
