# mariadb — Primary·Replica 구축 기록 (2026-11-20)

비밀번호는 쓰지 않는다. 계정 비밀번호는 팀장에게 개인 메시지로 받는다.

## 구성
| 항목 | Primary | Replica |
|---|---|---|
| VM | `mariadb-pr` (10.0.2.101) | `mariadb-re` (10.0.2.102) |
| 버전 | MariaDB 10.11.18 (Rocky Linux 10 AppStream) | 같음 |
| 역할 | 쓰기 + 읽기, `server-id=1` | 읽기 전용 `read_only=ON`, `server-id=2` |
| datadir | `/DATA/mysql` (디스크 4G) | `/DATA/mysql` (디스크 14G) |
| 설정 파일 | `/etc/my.cnf.d/zz-gamenuri.cnf` ← `zz-gamenuri.cnf.example` | 같음 (Replica 줄 주석 해제) |

복제: binlog 파일·위치 방식 (`mysql-bin.000001`, 4334부터). GTID 전환 예정.

## 설치 순서
```bash
hostname                                   # 대상 VM인지 먼저 확인
sudo dnf install -y mariadb-server mariadb
sudo mkdir -p /DATA/mysql && sudo chown mysql:mysql /DATA/mysql && sudo chmod 750 /DATA/mysql
sudo semanage fcontext -a -t mysqld_db_t "/DATA/mysql(/.*)?"
sudo restorecon -Rv /DATA/mysql
sudo cp zz-gamenuri.cnf.example /etc/my.cnf.d/zz-gamenuri.cnf   # server-id 등 VM에 맞게 수정
sudo mariadb-install-db --user=mysql --datadir=/DATA/mysql
sudo systemctl enable --now mariadb
sudo mariadb-secure-installation           # root 비밀번호, 익명·원격 root·test DB 제거
```
- 파일명이 `zz-`로 시작하는 이유: `/etc/my.cnf.d/`는 알파벳 순으로 읽혀 나중 값이 이긴다. 패키지 기본 `mariadb-server.cnf`의 `datadir=/var/lib/mysql`을 덮어쓰려고 맨 뒤로 보냈다.
- 방화벽: 10.0.0.0/16에서만 3306 허용.
- 계정 생성은 `init.sql`(템플릿) 참고.

## Replica 연결
1. Replica도 위와 같이 설치·초기화·보안 설정 (`server-id=2`, `read_only=ON`, `relay_log`, `log_slave_updates`)
2. Primary 전체 덤프를 Replica에 불러오고, 덤프에 적힌 binlog 위치로 연결
```sql
-- Replica에서
CHANGE MASTER TO MASTER_HOST='10.0.2.101', MASTER_USER='repl', MASTER_PASSWORD='<비밀번호>',
  MASTER_LOG_FILE='mysql-bin.000001', MASTER_LOG_POS=<덤프에 적힌 위치>;
START SLAVE;
SHOW SLAVE STATUS\G      -- Slave_IO_Running: Yes, Slave_SQL_Running: Yes, Seconds_Behind_Master: 0
```
3. 덤프 파일(`/tmp/full.sql`)은 계정 해시가 들어 있으니 끝나면 지운다.

## 확인 명령
```bash
mariadb -h mariadb-pr -u gamenuri -p gamenuri -e "SELECT @@hostname, @@time_zone;"
mariadb -h mariadb-re -u gamenuri -p gamenuri -e "SHOW TABLES;"
sudo mariadb -e "SHOW SLAVE STATUS\G"        # mariadb-re에서
```

## 규칙
- 쓰기·테이블 변경(`ALTER`)은 Primary에서만. Replica에 쓰면 복제가 멈춘다.
- Replica에서 root로 쓰지 않는다 (`read_only`는 root를 막지 못함).
- 테이블은 `docs/contracts/erd.sql`로만 만든다. DB VM 안에서 `gamenuri` 계정으로 접속할 때는 `localhost`가 아니라 자기 IP(`-h 10.0.2.101`).
- `DROP`, `TRUNCATE`는 팀장 확인 후.

## 겪은 문제
| 문제 | 원인 | 해결 |
|---|---|---|
| 복제 `Slave_SQL_Running: No` (`Can't find record in global_priv`) | binlog를 처음부터 재생했는데 Replica가 이미 같은 보안 설정을 해서 상태가 달랐음 | `RESET SLAVE ALL` → Primary 전체 덤프 로드 → 덤프의 binlog 위치로 재연결 |
| `1130 Host 'kafka1' is not allowed` | 접속 IP가 `/etc/hosts`로 이름 해석돼 `10.0.%`와 불일치 | 두 대에 `skip-name-resolve` |
| 재시작 직후 `Connection refused` | Primary 재시작 중 Replica 접속 시도 | 약 1분 뒤 자동 복구 |
| mongodb-pr에 MariaDB 설치 | MobaXterm 탭 혼동 | 패키지·디렉터리·semanage 규칙 제거. 명령 전 `hostname` 확인 |

## 남은 일
- [ ] 복제 GTID 전환 (`CHANGE MASTER TO MASTER_USE_GTID=slave_pos`)
- [ ] ERD 적용 후 계정 분리 (`gamenuri_connect`, `gamenuri_app`), `gamenuri`의 CREATE/ALTER/DROP 회수
- [ ] 모니터링 `exporter`@10.0.2.1, 백업 `backup`@10.0.1.108 계정 (11/25)
- [ ] Primary `/DATA` 4G binlog 용량 확인
