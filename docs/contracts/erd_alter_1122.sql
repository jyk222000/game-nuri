-- 이미 erd.sql(28개)을 적용한 서버를 11/22 변경에 맞춘다. 한 번만 실행한다.
-- 적용: mariadb-pr에서만 (Replica에는 복제로 반영된다)
--   mysql -u root -p gamenuri < erd_alter_1122.sql
-- 실행 전 확인: 가격 테이블이 비어 있어야 한다 (둘 다 0)
--   SELECT COUNT(*) FROM prices_current; SELECT COUNT(*) FROM price_history;
--   행이 있으면 새 NOT NULL 컬럼이 빈 문자열로 채워진다. 그때는 실행하지 말고 팀장과 상의한다.
-- 실행 순서: 이 파일 → Connect pk.fields 변경(남현식) → refiner 배포

-- 1) 가격: 플랫폼·상태 (prices_current는 PK에 포함)
ALTER TABLE prices_current
  ADD COLUMN platform VARCHAR(16) NOT NULL AFTER edition,
  ADD COLUMN item_condition VARCHAR(8) NOT NULL AFTER platform,
  DROP PRIMARY KEY,
  ADD PRIMARY KEY (game_id, store, edition, platform, item_condition);

ALTER TABLE price_history
  ADD COLUMN platform VARCHAR(16) NOT NULL AFTER edition,
  ADD COLUMN item_condition VARCHAR(8) NOT NULL AFTER platform,
  ADD INDEX idx_game_platform_time (game_id, platform, item_condition, collected_at);

-- 2) 게임: 평론 점수
ALTER TABLE games
  ADD COLUMN aggregated_rating DECIMAL(5,2) AFTER rating_count,
  ADD COLUMN aggregated_rating_count INT AFTER aggregated_rating;

-- 3) 플랫폼별 출시일
ALTER TABLE game_platforms
  ADD COLUMN release_date DATE AFTER platform;
