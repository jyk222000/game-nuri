-- 겜누리 MariaDB 스키마 — 바꿀 때는 contracts PR로
-- 시간: UTC DATETIME, 금액: 원화 INT
-- 적용: mariadb-pr(10.0.2.101)에서만. Replica에는 복제로 생긴다. (MariaDB 구축 문서 4장)
--   mariadb -h 10.0.2.101 -u gamenuri -p < erd.sql
--
-- 기준 문서: GitHub main docs/contracts, docs/collector-test/column-mapping.md, docs/features.md, docs/contracts/api.md
-- 이번 변경 (초안 15개 → 28개)
--   1) 1NF: games.genres / games.platforms 쉼표 문자열 → genres·platforms·companies + 연결 테이블 3개
--   2) 추가: game_aliases(한글명·줄임말 검색, 다나와 상품명 매칭), exchange_rates(원화 환산 기준)
--   3) price_history: refined.prices 메시지 필드 중 빠져 있던 price_original, currency_original, url 추가
--      (JDBC Sink insert는 메시지 필드를 모두 컬럼에 넣으므로, 없으면 적재가 실패한다)
--   4) game_store_ids: PK를 (store, external_id)로. 외부 번호 하나가 게임 둘에 붙지 않게 (게임 ID 통합)
--   5) column-mapping 1·9절 반영: games 상세 컬럼, game_time_to_beat.ttb_count, game_series·game_series_map(series_ids),
--      tags·game_tags(/api/tags), game_aliases 검수 여부(LLM 표기는 검수 후 사용, danawa-notes 14절),
--      stores.itad_shop_id(ITAD shops/v1), user_owned_games(④ 보유 게임·플레이타임, API 23·24)
--   ※ 가격 flags, 한국어 리뷰 수는 아직 넣지 않았다 (contracts_change_proposal.md 2·3번)
-- 11/22 추가 (팀장 검토 1·2·3번)
--   6) prices_current·price_history: platform, item_condition(new|used) 추가, prices_current PK에 포함
--      (같은 게임의 PS4·PS5, 신품·중고가 서로 덮어쓰지 않게. condition은 MariaDB 예약어라 item_condition)
--   7) games: aggregated_rating, aggregated_rating_count (IGDB 평론 점수, A3 평론 vs 유저)
--   8) game_platforms: release_date (플랫폼별 출시일, A6 콘솔→PC 지연, A8 경과 기간)
--   이미 적용된 서버는 erd_alter_1122.sql로 바꾼다
-- 11/23 추가
--   9) price_history: 유니크 키 (game_id, store, edition, platform, item_condition, collected_at)
--      ITAD 이력을 주마다 다시 받거나 같은 메시지가 두 번 와도 한 줄만 남게 (JDBC Sink upsert)
--   이미 적용된 서버는 erd_alter_1123.sql로 바꾼다
--
-- 규칙 (구축 문서 4장)
--   - 모든 테이블에 PRIMARY KEY
--   - Kafka Connect가 쓰는 테이블의 컬럼 이름 = docs/contracts/messages 필드 이름 (snake_case)
--   - 문자셋·엔진은 DB 기본값(utf8mb4, InnoDB)을 따르므로 테이블마다 적지 않는다
--   - Kafka Connect가 쓰는 테이블에는 FK·CHECK를 걸지 않는다
--     (토픽 도착 순서가 보장되지 않고, 제약에 걸리면 Sink 작업이 멈춘다)
CREATE DATABASE IF NOT EXISTS gamenuri DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE gamenuri;

-- =====================================================================
-- 1. 게임 (Kafka Connect: refined.games)
-- =====================================================================
CREATE TABLE games (
  game_id          BIGINT PRIMARY KEY,            -- IGDB ID (기준 키)
  name             VARCHAR(255) NOT NULL,         -- 영문 이름
  name_ko          VARCHAR(255),                  -- 한글 이름 (IGDB game_localizations, region=Korea)
  slug             VARCHAR(255),
  summary          TEXT,
  release_date     DATE,                          -- IGDB first_release_date (UTC)
  game_type        SMALLINT,                      -- IGDB game_type (본편·DLC·에디션 등)
  parent_game_id   BIGINT,                        -- IGDB parent_game: DLC·확장의 본편
  version_parent_id BIGINT,                       -- IGDB version_parent: 에디션의 원본
  cover_image_id   VARCHAR(64),                   -- IGDB cover.image_id (URL은 규칙으로 조합)
  cover_url        VARCHAR(512),
  rating           DECIMAL(5,2),                  -- IGDB total_rating
  rating_count     INT,
  aggregated_rating DECIMAL(5,2),                 -- IGDB aggregated_rating (평론 점수)
  aggregated_rating_count INT,                    -- IGDB aggregated_rating_count
  age_rating       SMALLINT,                      -- Steam required_age (문자·숫자 섞여 옴 → 정제에서 정수)
  korean_supported BOOLEAN,                       -- Steam supported_languages 파싱
  is_online        BOOLEAN,                       -- Steam categories(멀티플레이어 등)에서 파생 (⑦ 경고)
  updated_at       DATETIME NOT NULL,
  INDEX idx_games_name (name),
  INDEX idx_games_parent (parent_game_id)
);

CREATE TABLE platforms (                         -- 플랫폼 코드
  platform         VARCHAR(16) PRIMARY KEY,       -- PC, PS5, PS4, Switch, Switch2, XboxSeries, XboxOne
  display_name     VARCHAR(64) NOT NULL
);

CREATE TABLE genres (                            -- 장르 코드
  genre_id         INT PRIMARY KEY,               -- Steam 장르 번호
  name             VARCHAR(64) NOT NULL
);

CREATE TABLE companies (                         -- 개발사·배급사
  company_id       INT AUTO_INCREMENT PRIMARY KEY,
  name             VARCHAR(255) NOT NULL UNIQUE
);

CREATE TABLE game_platforms (                    -- 게임 N:M 플랫폼
  game_id          BIGINT NOT NULL,
  platform         VARCHAR(16) NOT NULL,
  release_date     DATE,                          -- 플랫폼별 출시일 (IGDB release_dates)
  PRIMARY KEY (game_id, platform)
);

CREATE TABLE game_genres (                       -- 게임 N:M 장르
  game_id          BIGINT NOT NULL,
  genre_id         INT NOT NULL,
  PRIMARY KEY (game_id, genre_id)
);

CREATE TABLE game_companies (                    -- 게임 N:M 회사
  game_id          BIGINT NOT NULL,
  company_id       INT NOT NULL,
  role             VARCHAR(16) NOT NULL,          -- developer | publisher
  PRIMARY KEY (game_id, company_id, role)
);

CREATE TABLE game_aliases (                      -- 별칭: 한글명·줄임말 검색, 다나와 상품명 매칭
  alias_id         BIGINT AUTO_INCREMENT PRIMARY KEY,
  game_id          BIGINT NOT NULL,
  alias            VARCHAR(255) NOT NULL,         -- 레데리2, 바이오하자드 RE:4 ...
  source           VARCHAR(16) NOT NULL,          -- igdb | llm | manual
  reviewed         BOOLEAN NOT NULL DEFAULT FALSE,-- 사람이 검수했는지. llm 표기는 검수 전 매칭·검색에 쓰지 않는다
  UNIQUE KEY uq_game_alias (game_id, alias),
  INDEX idx_alias (alias)
);

CREATE TABLE game_series (                       -- IGDB collections / franchises (상품 배정·제외 규칙 자동 생성)
  series_id        BIGINT NOT NULL,               -- IGDB collection 또는 franchise id
  kind             VARCHAR(16) NOT NULL,          -- collection | franchise (id 체계가 달라 PK에 포함)
  name             VARCHAR(255) NOT NULL,
  PRIMARY KEY (series_id, kind)
);

CREATE TABLE game_series_map (                   -- 게임 N:M 시리즈
  game_id          BIGINT NOT NULL,
  series_id        BIGINT NOT NULL,
  kind             VARCHAR(16) NOT NULL,
  PRIMARY KEY (game_id, series_id, kind)
);

CREATE TABLE tags (                              -- 필터 태그 (/api/tags): IGDB themes·keywords, ITAD tags
  tag_id           INT AUTO_INCREMENT PRIMARY KEY,
  name             VARCHAR(64) NOT NULL,
  source           VARCHAR(16) NOT NULL,          -- igdb_theme | igdb_keyword | itad
  name_ko          VARCHAR(64),                   -- 한국어 이름 매핑표로 채움
  UNIQUE KEY uq_tag (source, name)
);

CREATE TABLE game_tags (                         -- 게임 N:M 태그
  game_id          BIGINT NOT NULL,
  tag_id           INT NOT NULL,
  PRIMARY KEY (game_id, tag_id)
);

CREATE TABLE stores (
  store            VARCHAR(32) PRIMARY KEY,       -- steam, epic, gog, msstore, blizzard, ea, ubisoft, danawa
  display_name     VARCHAR(64) NOT NULL,
  platform         ENUM('pc','console') NOT NULL,
  itad_shop_id     INT UNIQUE                     -- ITAD service/shops/v1 id (Steam=61). 다나와는 NULL
);

CREATE TABLE game_store_ids (                    -- 외부 번호 → IGDB 게임 (게임 ID 통합)
  game_id          BIGINT NOT NULL,
  store            VARCHAR(32) NOT NULL,          -- steam | itad | danawa
  external_id      VARCHAR(128) NOT NULL,         -- Steam appid, ITAD id, 다나와 pcode 등
  PRIMARY KEY (store, external_id),               -- 외부 번호 하나는 게임 하나에만
  INDEX idx_game (game_id)
);

CREATE TABLE game_time_to_beat (                 -- IGDB 클리어 시간 (④)
  game_id          BIGINT PRIMARY KEY,
  hastily_sec      INT,                           -- 빠르게
  normally_sec     INT,                           -- 보통
  completely_sec   INT,                           -- 완벽하게
  ttb_count        INT,                           -- 집계 인원 (적으면 이상값 판단 근거)
  updated_at       DATETIME NOT NULL
);

CREATE TABLE game_requirements (                 -- Steam 최소·권장 사양 (⑥, Kafka Connect: refined.requirements)
  game_id          BIGINT PRIMARY KEY,
  minimum_text     TEXT,                          -- HTML 정리 후 텍스트
  recommended_text TEXT,
  updated_at       DATETIME NOT NULL
);

CREATE TABLE player_counts (                     -- Steam 동접자 추이 (⑦)
  game_id          BIGINT NOT NULL,
  player_count     INT NOT NULL,
  collected_at     DATETIME NOT NULL,
  PRIMARY KEY (game_id, collected_at)
);

CREATE TABLE review_summaries (                  -- ES 키워드 + AI 요약 (⑤, Kafka Connect: refined.review_summary)
  game_id          BIGINT PRIMARY KEY,
  positive_ratio   DECIMAL(4,3),
  pros_keywords    VARCHAR(512),                  -- 쉼표 구분 (표시용 요약)
  cons_keywords    VARCHAR(512),
  summary          VARCHAR(1000),
  generated_by     VARCHAR(16) NOT NULL,          -- ai | fallback
  updated_at       DATETIME NOT NULL
);

-- =====================================================================
-- 2. 가격 (Kafka Connect: refined.prices)
--    컬럼 = refined.prices 필드: game_id, store, edition, price_krw, regular_krw, discount_pct,
--                               price_original, currency_original, url, collected_at
-- =====================================================================
CREATE TABLE prices_current (                    -- JDBC Sink upsert (pk.fields = game_id,store,edition,platform,item_condition)
  game_id          BIGINT NOT NULL,
  store            VARCHAR(32) NOT NULL,
  edition          VARCHAR(16) NOT NULL,          -- digital | physical | code
  platform         VARCHAR(16) NOT NULL,          -- platforms.platform (PC, PS4, PS5, Switch ...)
  item_condition   VARCHAR(8) NOT NULL,           -- new | used
  price_krw        INT NOT NULL,                  -- 원화 환산 금액
  regular_krw      INT,
  discount_pct     INT,
  price_original   DOUBLE,                        -- 환산 전 금액
  currency_original VARCHAR(8),                   -- KRW | USD | EUR | GBP
  url              VARCHAR(512),
  collected_at     DATETIME NOT NULL,
  PRIMARY KEY (game_id, store, edition, platform, item_condition)
);

CREATE TABLE price_history (                     -- JDBC Sink insert
  id               BIGINT AUTO_INCREMENT PRIMARY KEY,
  game_id          BIGINT NOT NULL,
  store            VARCHAR(32) NOT NULL,
  edition          VARCHAR(16) NOT NULL,
  platform         VARCHAR(16) NOT NULL,
  item_condition   VARCHAR(8) NOT NULL,           -- new | used
  price_krw        INT NOT NULL,
  regular_krw      INT,
  discount_pct     INT,
  price_original   DOUBLE,
  currency_original VARCHAR(8),
  url              VARCHAR(512),
  collected_at     DATETIME NOT NULL,
  INDEX idx_game_time (game_id, collected_at),
  INDEX idx_game_platform_time (game_id, platform, item_condition, collected_at),
  UNIQUE KEY uq_price_history (game_id, store, edition, platform, item_condition, collected_at)
);

CREATE TABLE exchange_rates (                    -- 원화 환산 기준 (정제 단계에서 사용)
  rate_date        DATE NOT NULL,
  currency         CHAR(3) NOT NULL,              -- USD, EUR, GBP
  krw_per_unit     DECIMAL(12,4) NOT NULL,        -- 1단위당 원화
  PRIMARY KEY (rate_date, currency)
);

-- =====================================================================
-- 3. 사용자 · 알림 (Backend가 직접 씀) — 이 영역만 FK를 건다
-- =====================================================================
CREATE TABLE users (
  user_id          BIGINT AUTO_INCREMENT PRIMARY KEY,
  email            VARCHAR(255) NOT NULL UNIQUE,
  password_hash    VARCHAR(255),                  -- 구글 로그인 사용자는 NULL
  google_sub       VARCHAR(64) UNIQUE,            -- 구글 계정 고유 ID
  nickname         VARCHAR(64),
  steam_id         VARCHAR(32),
  created_at       DATETIME NOT NULL
);

CREATE TABLE user_specs (                        -- 사용자 PC 사양 (선택 입력, ⑥)
  user_id          BIGINT PRIMARY KEY,
  cpu              VARCHAR(128),
  gpu              VARCHAR(128),
  ram_gb           INT,
  os               VARCHAR(64),
  updated_at       DATETIME NOT NULL,
  CONSTRAINT fk_user_specs_user FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
);

CREATE TABLE notification_settings (            -- 메일 수신 설정 (③)
  user_id          BIGINT PRIMARY KEY,
  email_enabled    BOOLEAN NOT NULL DEFAULT TRUE,
  updated_at       DATETIME NOT NULL,
  CONSTRAINT fk_notification_user FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
);

CREATE TABLE user_owned_games (                  -- ④ Steam 보유 게임·플레이타임 (GetOwnedGames, 공개 프로필만)
  user_id          BIGINT NOT NULL,
  steam_appid      INT NOT NULL,                  -- Steam appid (game_store_ids로 IGDB 게임에 연결)
  playtime_forever_min INT NOT NULL DEFAULT 0,    -- 총 플레이 시간 (분)
  rtime_last_played DATETIME,                     -- 마지막 플레이 (UTC)
  updated_at       DATETIME NOT NULL,
  PRIMARY KEY (user_id, steam_appid),
  CONSTRAINT fk_owned_user FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
);

CREATE TABLE wishlists (
  user_id          BIGINT NOT NULL,
  game_id          BIGINT NOT NULL,
  created_at       DATETIME NOT NULL,
  PRIMARY KEY (user_id, game_id),
  CONSTRAINT fk_wishlists_user FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
);

CREATE TABLE alerts (
  alert_id         BIGINT AUTO_INCREMENT PRIMARY KEY,
  user_id          BIGINT NOT NULL,
  game_id          BIGINT NOT NULL,
  target_price_krw INT NOT NULL,
  active           BOOLEAN NOT NULL DEFAULT TRUE,
  created_at       DATETIME NOT NULL,
  UNIQUE KEY uq_user_game (user_id, game_id),
  CONSTRAINT fk_alerts_user FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
);

CREATE TABLE alert_logs (
  log_id           BIGINT AUTO_INCREMENT PRIMARY KEY,
  alert_id         BIGINT NOT NULL,
  price_krw        INT NOT NULL,
  store            VARCHAR(32) NOT NULL,
  sent_at          DATETIME NOT NULL,
  CONSTRAINT fk_alert_logs_alert FOREIGN KEY (alert_id) REFERENCES alerts (alert_id) ON DELETE CASCADE
);

-- =====================================================================
-- 4. 코드 테이블 기본값
-- =====================================================================
INSERT INTO platforms (platform, display_name) VALUES
  ('PC', 'PC'), ('PS5', 'PlayStation 5'), ('PS4', 'PlayStation 4'),
  ('Switch', 'Nintendo Switch'), ('Switch2', 'Nintendo Switch 2'),
  ('XboxSeries', 'Xbox Series X|S'), ('XboxOne', 'Xbox One');
