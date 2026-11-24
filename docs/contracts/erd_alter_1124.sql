-- 11/24: prices_current·price_history에 variant_name 추가 (erd.sql 11번, #93).
-- 에디션 가격(본편 상품이 없는 플랫폼)일 때 이름을 담는다. 본편은 NULL. 기존 줄은 NULL로 남는다.
-- 적용: mariadb-pr에서만 (Replica에는 복제로). **정제기 새 코드보다 먼저** 실행해야 한다
--   (칼럼이 없는데 variant_name이 오면 JDBC Sink가 멈춘다).
--   mysql -u root -p gamenuri < erd_alter_1124.sql
USE gamenuri;
ALTER TABLE prices_current ADD COLUMN IF NOT EXISTS variant_name VARCHAR(64) NULL AFTER url;
ALTER TABLE price_history ADD COLUMN IF NOT EXISTS variant_name VARCHAR(64) NULL AFTER url;
