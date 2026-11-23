-- 11/23: game_review_stats 추가 (erd.sql 9번). 이미 erd.sql을 적용한 서버에서 한 번만 실행한다.
-- 적용: mariadb-pr에서만. Replica에는 복제로 생긴다.
--   mysql -u root -p gamenuri < erd_alter_1123.sql
-- 새 테이블만 만든다 (기존 데이터는 건드리지 않음). 이미 있으면 아무 일도 하지 않는다.
USE gamenuri;

CREATE TABLE IF NOT EXISTS game_review_stats (   -- Steam 스토어 리뷰 수·긍정률 (Kafka Connect: refined.review_stats)
  game_id          BIGINT PRIMARY KEY,
  review_count_ko  INT,
  positive_pct_ko  SMALLINT,
  review_score_ko  SMALLINT,
  review_label_ko  VARCHAR(32),
  review_count_all INT,
  positive_pct_all SMALLINT,
  review_label_all VARCHAR(32),
  updated_at       DATETIME NOT NULL
);
