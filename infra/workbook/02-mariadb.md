# 2. MariaDB Primary · Replica (mariadb-pr, mariadb-re)

가격·게임·사용자 데이터를 저장하는 DB입니다. **mariadb-pr(Primary)** 에 쓰고, **mariadb-re(Replica)** 가 복제해서 읽기를 나눠 맡습니다.
테이블(28개)은 이고은 담당의 `docs/contracts/erd.sql`로 만듭니다. 이 문서는 서버 설치·복제·계정까지입니다.
(구축 2026-11-20, `infra/mariadb/README.md`가 원본 기록)

## 0. 만드는 것
```
Kafka Connect ──쓰기──▶ [mariadb-pr 10.0.2.101]  server-id=1, 쓰기+읽기
Backend(사용자·알림) ──쓰기──▶      │ binlog(ROW)
                                   ▼ 복제
Backend(조회) ──읽기──▶ [mariadb-re 10.0.2.102]  server-id=2, read_only=ON
```
| 항목 | Primary | Replica |
|---|---|---|
| VM | mariadb-pr (10.0.2.101) | mariadb-re (10.0.2.102) |
| 버전 | MariaDB 10.11.18 (Rocky Linux 10 AppStream) | 같음 |
| 데이터 폴더 | `/DATA/mysql` (디스크 4G) | `/DATA/mysql` (디스크 14G) |
| 설정 파일 | `/etc/my.cnf.d/zz-gamenuri.cnf` | 같음 (Replica 줄 주석 해제) |

> <- 복제 방식은 binlog 파일·위치 방식입니다(GTID 전환은 남은 일). Backend는 읽기를 Replica에서, **내 데이터(찜·알림 직후 조회)는 Primary에서** 읽습니다(복제 지연 때문).

## 1. 설치 (두 대 모두 같은 순서)
```
# 대상 VM이 맞는지 먼저 확인 (잘못된 VM에 설치한 적이 있음)
[admina@mariadb-pr ~]$ hostname

# MariaDB 서버·클라이언트 설치
[admina@mariadb-pr ~]$ sudo dnf install -y mariadb-server mariadb

# 데이터 폴더 만들기: 소유자 mysql, 권한 750
[admina@mariadb-pr ~]$ sudo mkdir -p /DATA/mysql && sudo chown mysql:mysql /DATA/mysql && sudo chmod 750 /DATA/mysql

# SELinux 라벨 지정 (이 폴더를 MariaDB 데이터 폴더로 인정)
[admina@mariadb-pr ~]$ sudo semanage fcontext -a -t mysqld_db_t "/DATA/mysql(/.*)?"
[admina@mariadb-pr ~]$ sudo restorecon -Rv /DATA/mysql
```
> <- SELinux 는 Enforcing 그대로 둡니다. 라벨이 안 맞으면 MariaDB가 `/DATA` 에 못 씁니다.
> <- `semanage` 명령이 없으면 `sudo dnf install -y policycoreutils-python-utils` (⚠ 미확인: 이 서버에서 필요했는지 기록 없음).

## 2. 설정 파일
```
# 예시 파일을 복사 (레포: infra/mariadb/zz-gamenuri.cnf.example)
[admina@mariadb-pr ~]$ sudo cp /opt/game-nuri/repo/infra/mariadb/zz-gamenuri.cnf.example /etc/my.cnf.d/zz-gamenuri.cnf
```
파일 내용(핵심):
```
> [mysqld]
> skip-name-resolve
> datadir=/DATA/mysql
> bind-address=0.0.0.0
> log_bin=mysql-bin
> binlog_format=ROW
> binlog_expire_logs_seconds=259200
> character-set-server=utf8mb4
> collation-server=utf8mb4_unicode_ci
> default_time_zone='+00:00'
> innodb_buffer_pool_size=512M
> server-id=1
```
> <- Replica(mariadb-re)에서는 `server-id=1` 대신 `server-id=2`, 그리고 `relay_log=relay-bin`, `read_only=ON`, `log_slave_updates=ON` 을 켭니다.
> <- 파일 이름이 `zz-`로 시작하는 이유: `/etc/my.cnf.d/` 는 알파벳 순으로 읽히고 **나중 값이 이깁니다**. 패키지 기본 `datadir=/var/lib/mysql` 을 덮어쓰려고 맨 뒤로 보냈습니다.
> <- `skip-name-resolve`: 접속 허용을 IP 패턴(`10.0.%`)으로만 하려고 켭니다. 안 켜면 `/etc/hosts` 이름(`kafka1`)으로 해석돼 `1130 Host 'kafka1' is not allowed` 가 납니다.
> <- `default_time_zone='+00:00'`: 시간은 항상 UTC로 저장하는 팀 규칙입니다. binlog는 3일(259200초) 보관합니다. Primary `/DATA`가 4G라서 짧게 둡니다.

```
# 데이터 폴더 초기화 후 서비스 시작
[admina@mariadb-pr ~]$ sudo mariadb-install-db --user=mysql --datadir=/DATA/mysql
[admina@mariadb-pr ~]$ sudo systemctl enable --now mariadb

# 보안 마법사: root 비밀번호 설정, 익명 사용자·원격 root·test DB 제거
[admina@mariadb-pr ~]$ sudo mariadb-secure-installation
```
> <- 마법사의 비밀번호는 입력창에 직접 칩니다. 문서·채팅에 남기지 않습니다.

## 3. 계정과 DB
`infra/mariadb/init.sql` 이 템플릿입니다. **Primary에서만** 실행하고, 비밀번호는 `<비밀번호>` 자리에 직접 입력합니다(파일을 커밋하지 않음).
```
# Primary 에서 root 로 접속
[admina@mariadb-pr ~]$ sudo mariadb

# DB 만들기 (아래는 mariadb 안에서 입력)
> CREATE DATABASE IF NOT EXISTS gamenuri DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```
| 계정 | 접속 허용 | 권한 | 상태 |
|---|---|---|---|
| `gamenuri` | `10.0.%` | `gamenuri` DB의 SELECT·INSERT·UPDATE·DELETE·CREATE·ALTER·INDEX·DROP (앱 공용, 현재) | 사용 중 |
| `repl` | `10.0.2.102` | REPLICATION SLAVE, REPLICATION CLIENT (복제) | 사용 중 |
| `gamenuri_connect` | `10.0.1.%` | 가격·게임 테이블 INSERT·UPDATE (Kafka Connect) | 계획 |
| `gamenuri_app` | `10.0.1.%` | 전체 SELECT + 사용자·알림 7개 테이블 INSERT·UPDATE·DELETE (Backend) | 계획 |
| `exporter` | `10.0.2.1` | PROCESS, REPLICATION CLIENT, SELECT (모니터링) | 계획 (11/25) |
| `backup` | `10.0.1.108` | SELECT, SHOW VIEW, TRIGGER, LOCK TABLES, EVENT (백업) | 계획 (11/25), ⚠ 생성 여부 미확인 |

> <- Backend가 쓰는 테이블은 사용자·알림 7개(`users`, `user_specs`, `notification_settings`, `user_owned_games`, `wishlists`, `alerts`, `alert_logs`)뿐입니다.
> **가격·게임 테이블은 DB 권한(SELECT만)으로 막는 것이 진짜 방어선**입니다. 앱의 쓰기 가드는 직접 SQL을 막지 못합니다.
> <- 현재는 공용 `gamenuri` 계정이 CREATE·DROP 권한까지 갖고 있습니다. ERD 적용 뒤 계정을 나누고 그 권한을 회수할 예정입니다(남은 일).

## 4. Replica 연결 (복제 시작)
복제용 계정 `repl` 은 Primary에서 만들고, 복제 시작은 Replica에서 합니다.
```
# (Primary) 복제 계정 생성 — 비밀번호는 직접 입력, 문서에 쓰지 않음
> CREATE USER 'repl'@'10.0.2.102' IDENTIFIED BY '<비밀번호>';
> GRANT REPLICATION SLAVE, REPLICATION CLIENT ON *.* TO 'repl'@'10.0.2.102';
```
1. Replica도 1~2장과 같이 설치·초기화·보안 설정합니다(`server-id=2`, `read_only=ON`, `relay_log`, `log_slave_updates`).
2. **Primary 전체 덤프**를 Replica에 불러오고, 덤프에 적힌 binlog 위치로 연결합니다.
```
# (Primary) 전체 덤프. binlog 위치가 덤프 맨 위에 주석으로 남는다
[admina@mariadb-pr ~]$ sudo mariadb-dump --all-databases --single-transaction --master-data=2 > /tmp/full.sql

# (Replica) 덤프 불러오기
[admina@mariadb-re ~]$ sudo mariadb < /tmp/full.sql
```
> <- ⚠ 미확인: 기록에는 "전체 덤프를 불러오고 덤프에 적힌 binlog 위치로 연결"만 있고, 정확한 덤프 옵션은 남아 있지 않습니다. 위 `--master-data=2`는 그 목적의 표준 방식입니다.
> <- 덤프 파일에는 계정 해시가 들어 있습니다. **끝나면 `/tmp/full.sql`을 지웁니다**(`⚠ 되돌릴 수 없음`: 지우기 전에 Replica에 불러온 결과를 확인).

```
# (Primary) 덤프 파일 맨 위 주석에서 binlog 파일 이름과 위치 찾기
[admina@mariadb-pr ~]$ grep -m1 "CHANGE MASTER" /tmp/full.sql

# (Replica) 복제 연결
> CHANGE MASTER TO MASTER_HOST='10.0.2.101', MASTER_USER='repl', MASTER_PASSWORD='<비밀번호>',
>   MASTER_LOG_FILE='mysql-bin.000001', MASTER_LOG_POS=<덤프에 적힌 위치>;
> START SLAVE;
> SHOW SLAVE STATUS\G
```
> <- 성공 기준: `Slave_IO_Running: Yes`, `Slave_SQL_Running: Yes`, `Seconds_Behind_Master: 0`.

## 5. 확인
```
# 두 서버에 접속되는지 (DB VM 안에서는 localhost 가 아니라 자기 IP 로 접속)
[admina@backend1 ~]$ mariadb -h mariadb-pr -u gamenuri -p gamenuri -e "SELECT @@hostname, @@time_zone;"
[admina@backend1 ~]$ mariadb -h mariadb-re -u gamenuri -p gamenuri -e "SHOW TABLES;"

# (Replica) 복제 상태
[admina@mariadb-re ~]$ sudo mariadb -e "SHOW SLAVE STATUS\G"
```
> <- 11/24에 `variant_name` 칸을 Primary에서 추가한 뒤 Primary와 Replica 모두 칸이 있고 복제 지연이 0임을 확인했습니다.

## 6. 규칙
- 쓰기·테이블 변경(`ALTER`)은 **Primary에서만**. Replica에 쓰면 복제가 멈춥니다. Replica에서 root로 쓰지 않습니다(`read_only`는 root를 막지 못함).
- 테이블은 `docs/contracts/erd.sql`로만 만듭니다. 칸을 추가하는 코드를 배포하기 **전에** DB에 칸을 먼저 추가합니다(반대면 조회가 오류).
- `DROP`, `TRUNCATE`는 팀장 확인 후에만 합니다. `⚠ 되돌릴 수 없음`

## 7. 겪은 문제
| 문제 | 원인 | 해결 |
|---|---|---|
| 복제 `Slave_SQL_Running: No` (`Can't find record in global_priv`) | binlog를 처음부터 재생했는데 Replica가 이미 같은 보안 설정을 해서 상태가 달랐음 | `RESET SLAVE ALL` → Primary 전체 덤프 로드 → 덤프의 binlog 위치로 재연결 |
| `1130 Host 'kafka1' is not allowed` | 접속 IP가 `/etc/hosts`로 이름 해석돼 `10.0.%`와 불일치 | 두 대에 `skip-name-resolve` |
| 재시작 직후 `Connection refused` | Primary 재시작 중 Replica 접속 시도 | 약 1분 뒤 자동 복구 |
| mongodb-pr에 MariaDB 설치 | MobaXterm 탭 혼동 | 패키지·디렉터리·semanage 규칙 제거. **명령 전에 `hostname` 확인** |

## 8. 남은 일
- [ ] 복제 GTID 전환 (`CHANGE MASTER TO MASTER_USE_GTID=slave_pos`)
- [ ] ERD 적용 후 계정 분리(`gamenuri_connect`, `gamenuri_app`), `gamenuri`의 CREATE/ALTER/DROP 회수
- [ ] 모니터링 `exporter`, 백업 `backup` 계정
- [ ] Primary `/DATA` 4G의 binlog 용량 확인
