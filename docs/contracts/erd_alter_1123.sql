-- 11/23: price_history 중복 방지 유니크 키. mariadb-pr에서만, 한 번만 실행한다.
-- 실행 전 확인: 아래 쿼리가 0이어야 한다 (중복이 있으면 유니크 키를 만들 수 없음 → 팀장과 상의)
--   SELECT COUNT(*) FROM (SELECT 1 FROM price_history
--     GROUP BY game_id, store, edition, platform, item_condition, collected_at HAVING COUNT(*) > 1) d;
-- 실행 순서: 이 파일 → Connect price-history 커넥터를 upsert로 변경(남현식) → refiner 배포
ALTER TABLE price_history
  ADD UNIQUE KEY uq_price_history (game_id, store, edition, platform, item_condition, collected_at);
