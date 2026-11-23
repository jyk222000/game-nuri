-- 11/23: stores 기본값 8곳 (erd.sql 10번). mariadb-pr에서만 실행 (Replica에는 복제로 들어간다).
--   mysql -u root -p gamenuri < erd_seed_stores_1123.sql
-- 이미 있는 코드는 건너뛴다 (INSERT IGNORE). 다른 테이블은 건드리지 않는다.
USE gamenuri;
INSERT IGNORE INTO stores (store, display_name, platform, itad_shop_id) VALUES
  ('steam', 'Steam', 'pc', 61), ('epic', 'Epic Games Store', 'pc', NULL), ('gog', 'GOG', 'pc', NULL),
  ('msstore', 'Microsoft Store', 'pc', NULL), ('blizzard', 'Battle.net', 'pc', NULL),
  ('ea', 'EA app', 'pc', NULL), ('ubisoft', 'Ubisoft Store', 'pc', NULL),
  ('danawa', '다나와', 'console', NULL);
