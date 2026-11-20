-- 계정 생성 템플릿 (Primary에서 sudo mariadb 로 실행). 비밀번호는 직접 입력하고 커밋하지 않는다.
-- 테이블은 docs/contracts/erd.sql 로 만든다.
CREATE DATABASE IF NOT EXISTS gamenuri DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- 현재 (11/20): 앱 공용 계정. ERD 적용 후 CREATE/ALTER/DROP/INDEX 회수 예정
-- CREATE USER 'gamenuri'@'10.0.%' IDENTIFIED BY '<비밀번호>';
-- GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, INDEX, DROP ON gamenuri.* TO 'gamenuri'@'10.0.%';

-- 복제 (Replica만)
-- CREATE USER 'repl'@'10.0.2.102' IDENTIFIED BY '<비밀번호>';
-- GRANT REPLICATION SLAVE, REPLICATION CLIENT ON *.* TO 'repl'@'10.0.2.102';

-- 계획: 용도별 계정 분리
-- 'gamenuri_connect'@'10.0.1.%'  Kafka Connect: 가격·게임 테이블 INSERT, UPDATE
-- 'gamenuri_app'@'10.0.1.%'      Backend: 전체 SELECT + 사용자·알림 테이블 INSERT, UPDATE, DELETE
-- 'exporter'@'10.0.2.1'          모니터링: PROCESS, REPLICATION CLIENT, SELECT
-- 'backup'@'10.0.1.108'          백업: SELECT, SHOW VIEW, TRIGGER, LOCK TABLES, EVENT
