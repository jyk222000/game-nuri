-- 겜누리 MariaDB 스키마 (초안) — 바꿀 때는 contracts PR로
-- 시간: UTC DATETIME, 금액: 원화 INT
CREATE DATABASE IF NOT EXISTS gamenuri DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE gamenuri;

-- ===== 게임 (Kafka Connect: refined.games) =====
CREATE TABLE games (
  game_id          BIGINT PRIMARY KEY,            -- IGDB ID
  name             VARCHAR(255) NOT NULL,
  name_ko          VARCHAR(255),
  release_date     DATE,
  cover_url        VARCHAR(512),
  genres           VARCHAR(255),                  -- 쉼표 구분
  platforms        VARCHAR(255),
  updated_at       DATETIME NOT NULL
);

CREATE TABLE stores (
  store            VARCHAR(32) PRIMARY KEY,       -- steam, epic, gog, msstore, blizzard, ea, ubisoft, danawa
  display_name     VARCHAR(64) NOT NULL,
  platform         ENUM('pc','console') NOT NULL
);

CREATE TABLE game_store_ids (
  game_id          BIGINT NOT NULL,
  store            VARCHAR(32) NOT NULL,
  external_id      VARCHAR(128) NOT NULL,         -- Steam appid, ITAD id, 다나와 pcode 등
  PRIMARY KEY (game_id, store, external_id),
  INDEX idx_external (store, external_id)
);

CREATE TABLE game_time_to_beat (                 -- IGDB 클리어 시간 (④)
  game_id          BIGINT PRIMARY KEY,
  hastily_sec      INT,                           -- 빠르게
  normally_sec     INT,                           -- 보통
  completely_sec   INT,                           -- 완벽하게
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
  pros_keywords    VARCHAR(512),                  -- 쉼표 구분
  cons_keywords    VARCHAR(512),
  summary          VARCHAR(1000),
  generated_by     VARCHAR(16) NOT NULL,          -- ai | fallback
  updated_at       DATETIME NOT NULL
);

-- ===== 가격 (Kafka Connect: refined.prices) =====
CREATE TABLE prices_current (                    -- JDBC Sink upsert (PK 기준)
  game_id          BIGINT NOT NULL,
  store            VARCHAR(32) NOT NULL,
  edition          VARCHAR(16) NOT NULL,          -- digital | physical | code
  price_krw        INT NOT NULL,
  regular_krw      INT,
  discount_pct     INT,
  price_original   DOUBLE,
  currency_original VARCHAR(8),
  url              VARCHAR(512),
  collected_at     DATETIME NOT NULL,
  PRIMARY KEY (game_id, store, edition)
);

CREATE TABLE price_history (                     -- JDBC Sink insert
  id               BIGINT AUTO_INCREMENT PRIMARY KEY,
  game_id          BIGINT NOT NULL,
  store            VARCHAR(32) NOT NULL,
  edition          VARCHAR(16) NOT NULL,
  price_krw        INT NOT NULL,
  regular_krw      INT,
  discount_pct     INT,
  collected_at     DATETIME NOT NULL,
  INDEX idx_game_time (game_id, collected_at)
);

-- ===== 사용자 · 알림 (Backend가 직접 씀) =====
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
  updated_at       DATETIME NOT NULL
);

CREATE TABLE notification_settings (            -- 메일 수신 설정 (③)
  user_id          BIGINT PRIMARY KEY,
  email_enabled    BOOLEAN NOT NULL DEFAULT TRUE,
  updated_at       DATETIME NOT NULL
);

CREATE TABLE wishlists (
  user_id          BIGINT NOT NULL,
  game_id          BIGINT NOT NULL,
  created_at       DATETIME NOT NULL,
  PRIMARY KEY (user_id, game_id)
);

CREATE TABLE alerts (
  alert_id         BIGINT AUTO_INCREMENT PRIMARY KEY,
  user_id          BIGINT NOT NULL,
  game_id          BIGINT NOT NULL,
  target_price_krw INT NOT NULL,
  active           BOOLEAN NOT NULL DEFAULT TRUE,
  created_at       DATETIME NOT NULL,
  UNIQUE KEY uq_user_game (user_id, game_id)
);

CREATE TABLE alert_logs (
  log_id           BIGINT AUTO_INCREMENT PRIMARY KEY,
  alert_id         BIGINT NOT NULL,
  price_krw        INT NOT NULL,
  store            VARCHAR(32) NOT NULL,
  sent_at          DATETIME NOT NULL
);
