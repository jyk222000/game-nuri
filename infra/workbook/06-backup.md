# 6. 백업 (backup 서버)

**MariaDB와 MongoDB를 매일 새벽 3시에 덤프**해서 별도 디스크 `/BACKUP` 에 **7일** 보관합니다.
백업 서버는 PC-1에 있어, DB(PC-2)와 **다른 PC**에 사본이 남습니다(PC 하나가 고장 나도 복구 가능).
(스크립트 `infra/backup/backup.sh`, cron 예시 `infra/backup/crontab`)

## 11/25 서버 확인 결과 (backup 서버, 읽기 전용 확인)
| 항목 | 결과 | 의미 |
|---|---|---|
| `/BACKUP` 디스크 | **있음**. `sda3` 80G가 `/BACKUP` 에 마운트, 사용 24K | 디스크는 준비됨 |
| `mariadb-dump`, `mongodump` | **설치 안 됨** | 1장부터 설치 필요 |
| 레포 (`/opt/game-nuri`) | **비어 있음** (레포가 없음) | 스크립트를 가져와야 함 (2장 전에 1장의 3번) |
| `/etc/game-nuri/backup.env` | **없음** | 4장에서 만듦 |
| cron | **없음** (`no crontab for root`) | 7장에서 등록 |
| 쌓인 백업, 로그 | **없음** (`lost+found` 뿐) | 한 번도 실행된 적 없음 |
| MariaDB `backup` 계정 | **없음** | 3장에서 만듦 |
| MongoDB `backup` 계정 | **없음** | 3장에서 만듦 |

> <- 즉 **11/25 기준 백업은 아직 한 번도 돌지 않았습니다.** 아래 1~7장 순서대로 구성한 뒤 8장 복구 시험까지 하면 완성입니다. 완료한 항목은 10장의 체크를 채웁니다.
> <- 아직 확인하지 못한 것: `/BACKUP` 의 파일시스템 종류와 `/etc/fstab` 등록 여부(재부팅 후에도 마운트되는지).

## 0. 만드는 것
```
backup(10.0.1.108, PC-1) ──mariadb-dump──▶ mariadb-re(Replica)   ← Primary 부담을 안 주려고 Replica 에서 읽음
                         ──mongodump─────▶ MongoDB(secondary 우선)
                         └─▶ /BACKUP/YYYY-MM-DD/mariadb.sql.gz, mongo.archive.gz   (7일 보관)
```
| 항목 | 값 |
|---|---|
| 서버 | backup (10.0.1.108, PC-1) |
| 백업 디스크 | `/BACKUP` (별도 디스크 `sda3`, 약 80G) |
| 실행 | cron, 매일 03:00 (OS 시간대 Asia/Seoul 기준) |
| 보관 | 7일(날짜 폴더 `20??-??-??` 만 지움) |
| 설정 | `/etc/game-nuri/backup.env` (Git에 없음) |

백업하는 것/안 하는 것:
| 대상 | 백업 | 이유 |
|---|---|---|
| MariaDB `gamenuri` 전체 | 함 | 정제값·사용자·알림 |
| MongoDB `reviews`, `games` | 함 | 리뷰 원본(재수집 비용이 큼), 게임 정보 |
| MongoDB `raw_*`, `unmatched` | (같이 덤프됨) | 스크립트는 DB 전체를 덤프. `raw_*` 는 TTL 14일이라 복구해도 의미가 작음 |

> <- 스크립트가 `gamenuri_raw` 전체를 한 파일로 덤프합니다. "`raw_*` 를 빼는" 옵션은 현재 없습니다(⚠ 필요하면 `--excludeCollection` 로 개선 가능).

## 1. 준비 (backup 서버)
```
# 대상 VM인지 확인
[admina@backup ~]$ hostname

# MariaDB 클라이언트 (mariadb-dump 명령 포함)
[admina@backup ~]$ sudo dnf install -y mariadb

# MongoDB 백업 도구 (mongodump). MongoDB 공식 저장소가 필요
[admina@backup ~]$ sudo cp /opt/game-nuri/repo/infra/mongodb/mongodb-org-8.0.repo.example /etc/yum.repos.d/mongodb-org-8.0.repo
[admina@backup ~]$ sudo dnf install -y mongodb-database-tools
```

```
# 레포 받기 (backup 서버에는 레포가 없었음). 스크립트(infra/backup/backup.sh)를 쓰기 위해 필요
[admina@backup ~]$ cd /opt/game-nuri
[admina@backup game-nuri]$ git clone https://github.com/jyk222000/game-nuri.git repo

# 스크립트가 있는지 확인
[admina@backup game-nuri]$ ls -l /opt/game-nuri/repo/infra/backup/backup.sh
```
> <- 레포 접근에 인증이 필요해 clone이 안 되면, backend1에서 파일 하나만 복사합니다: `scp /opt/game-nuri/repo/infra/backup/backup.sh admina@backup:/tmp/` 후 backup 서버에서 `/opt/game-nuri/repo/infra/backup/` 를 만들어 넣습니다.
> <- 이후 이 문서의 스크립트 경로는 모두 `/opt/game-nuri/repo/infra/backup/backup.sh` 입니다.

> <- 11/25 확인: 두 도구가 **설치돼 있지 않았습니다**. 설치 후 `command -v mariadb-dump mongodump` 로 경로가 나오는지 확인합니다.
> <- 레포가 `/opt/game-nuri/repo` 가 아니라 `/opt/game-nuri/infra/backup/backup.sh` 에 있는 것으로 `crontab` 예시가 적혀 있습니다. **실제 경로를 확인한 뒤** 7장의 cron 줄을 맞춥니다(`ls /opt/game-nuri`).

## 2. 백업 디스크 `/BACKUP`
```
# 백업 디스크가 붙어 있는지 확인 (sda3, 약 80G)
[admina@backup ~]$ lsblk
[admina@backup ~]$ df -h /BACKUP

# 마운트가 안 돼 있으면 fstab 에 UUID 로 등록 (디스크 이름은 바뀔 수 있어 UUID 사용)
[admina@backup ~]$ sudo blkid /dev/sda3
> /dev/sda3: UUID="<위에서 나온 값>" TYPE="xfs"
```
> <- `/BACKUP` 이 마운트돼 있지 않으면 **백업이 루트 디스크(`/`)에 쌓여 서버가 멈출 수 있습니다.** 스크립트는 `/BACKUP` 폴더가 없으면 실패하고 중단합니다(루트 폴더는 만들지 않음).
> <- 11/25 확인: `sda3` 80G 가 `/BACKUP` 에 마운트돼 있습니다. ⚠ 미확인: 파일시스템 종류와 fstab 등록(`grep BACKUP /etc/fstab` 으로 확인). 위 `TYPE` 은 예시입니다. `docs/infra-status.md` 미해결 9번(`/backup` vs `/BACKUP` 경로)은 `backup.sh` 에서 `/BACKUP` 으로 정리됐습니다(커밋 `fe2b128`).

## 3. 백업용 읽기 전용 계정
백업 계정은 **읽기만** 가능하게 만듭니다. 비밀번호는 입력창으로 받고 문서·채팅에 쓰지 않습니다.
```
# (mariadb-pr, Primary 에서 한 번) 백업 계정: SELECT 등만. 10.0.1.108(backup)에서만 접속 허용
[admina@mariadb-pr ~]$ sudo mariadb
> CREATE USER 'backup'@'10.0.1.108' IDENTIFIED BY '<비밀번호>';
> GRANT SELECT, SHOW VIEW, TRIGGER, LOCK TABLES, EVENT ON gamenuri.* TO 'backup'@'10.0.1.108';
```
```
# (mongodb-pr, PRIMARY 에서 한 번) 백업 계정: gamenuri_raw 읽기만. 비밀번호는 입력창으로
> db.getSiblingDB("admin").createUser({user: "backup", pwd: passwordPrompt(), roles: [{role: "read", db: "gamenuri_raw"}]})
```
> <- 복제 중이므로 MariaDB 계정은 Primary에서 만들면 Replica에도 복제됩니다. 덤프는 Replica(`mariadb-re`)에서 읽습니다.
> <- `mongodump` 는 `find`·`listCollections`·`listIndexes` 만 필요해서 `read` 로 충분합니다. 11/25 확인: 두 계정 모두 **아직 없습니다**(MariaDB `mysql.user`, MongoDB `getUsers` 결과가 비어 있음).

## 4. 환경 파일 `/etc/game-nuri/backup.env`
```
# 환경 파일 만들기 (root 만 읽게). 값은 직접 입력
[admina@backup ~]$ sudo mkdir -p /etc/game-nuri
[admina@backup ~]$ sudo install -m 0600 -o root -g root /dev/null /etc/game-nuri/backup.env
[admina@backup ~]$ sudo vi /etc/game-nuri/backup.env
```
파일에 넣을 이름(값은 서버에만):
```
> MARIADB_PASSWORD=<backup 계정 비밀번호>
> MONGO_URI=mongodb://backup:<비밀번호>@mongodb-pr:27017,mongo-se1:27017,mongo-se2:27017/gamenuri_raw?replicaSet=rs0&authSource=admin
> # BACKUP_ROOT=/BACKUP      # 선택. 기본값이 /BACKUP
```
> <- 필수 값은 `MARIADB_PASSWORD`, `MONGO_URI` 입니다. 이 파일은 Git에 올리지 않습니다.
> <- `MONGO_URI` 의 비밀번호에 `@`, `:`, `/` 가 있으면 URL 인코딩합니다.
> <- 스크립트는 DB 비밀번호를 **명령줄(`ps`)에 보이지 않게** 임시 옵션 파일로 넘기고 끝나면 지웁니다. `mongodump --uri` 는 계정 정보가 명령줄에 보이므로 backup 서버는 팀 계정만 접속하게 합니다.

## 5. 스크립트가 하는 일 (`infra/backup/backup.sh`)
| 순서 | 동작 | 이유 |
|---|---|---|
| 1 | `/BACKUP` 폴더가 없으면 **즉시 실패** | 디스크가 안 붙은 채 루트 디스크가 차는 사고 방지 |
| 2 | `/BACKUP/오늘날짜/` 폴더 생성 | 날짜별 보관 |
| 3 | `mariadb-dump --single-transaction` → Replica(`mariadb-re`)에서 읽어 `mariadb.sql.gz.tmp` | 테이블을 잠그지 않고 일관된 스냅샷, Primary 부담 없음 |
| 4 | 끝나면 `.tmp` 를 정식 이름(`mariadb.sql.gz`)으로 바꿈 | 쓰는 도중 실패해도 반쪽 파일이 정상 백업처럼 남지 않게 |
| 5 | `mongodump --readPreference=secondary --gzip --archive=...` → `mongo.archive.gz` | Secondary에서 읽어 서비스 부하를 줄임 |
| 6 | 7일이 지난 `20??-??-??` 폴더만 삭제 | 그 밖의 폴더·파일은 건드리지 않음 |
| 7 | `backup ok 날짜` 출력 | 로그에서 성공 여부 확인 |

## 6. 수동으로 한 번 실행 (먼저 해 본다)
```
# 스크립트 실행 권한 확인
[admina@backup ~]$ ls -l /opt/game-nuri/repo/infra/backup/backup.sh

# 한 번 직접 실행 (스냅샷 후, 서비스 영향이 적은 시간에)
[admina@backup ~]$ sudo /opt/game-nuri/repo/infra/backup/backup.sh
> backup ok 2026-11-25

# 결과 파일과 크기 확인
[admina@backup ~]$ ls -lh /BACKUP/$(date +%F)/
```
> <- 성공 기준: `mariadb.sql.gz` 와 `mongo.archive.gz` 가 둘 다 있고 크기가 0이 아닙니다. `.tmp` 파일이 남아 있으면 중간에 실패한 것입니다.
> <- 실패하면 `backup FAILED: ...` 메시지가 나옵니다. 흔한 원인: `/BACKUP` 미마운트, 계정·비밀번호 오류, 네트워크(`mariadb-re`, MongoDB 접속).

## 7. 매일 자동 실행 (cron)
```
# root 의 cron 에 한 줄 추가 (편집기가 열린다)
[admina@backup ~]$ sudo crontab -e
> # KST 03:00 (OS 시간대 Asia/Seoul)
> 0 3 * * * /opt/game-nuri/repo/infra/backup/backup.sh >> /var/log/game-nuri-backup.log 2>&1

# 등록 확인
[admina@backup ~]$ sudo crontab -l
```
> <- 경로는 레포가 있는 실제 위치로 맞춥니다(`infra/backup/crontab` 예시는 `/opt/game-nuri/infra/backup/backup.sh`).
> <- 03:00은 서비스 이용이 적은 시간입니다. 같은 시각에 DB 부하가 큰 작업(수집 타이머)이 겹치지 않는지 확인합니다. 수집기 타이머는 00·06·12·18시대와 매일 03:00(IGDB, proxy)에 도는 것이 있습니다.
> <- 다음 날 아침에 `tail /var/log/game-nuri-backup.log` 로 `backup ok` 가 찍혔는지 봅니다.

## 8. 복구 시험 (⚠ 이 절차는 아직 실행한 기록이 없음)
백업은 **복구해 봐야** 믿을 수 있습니다. **운영 DB에 덮어쓰지 말고 시험용 DB에** 풀어 봅니다.
```
# (MariaDB) 시험용 빈 DB 만들기 — Primary 에서 (운영 DB 'gamenuri' 는 건드리지 않는다)
[admina@mariadb-pr ~]$ sudo mariadb -e "CREATE DATABASE gamenuri_restore_test"

# 덤프를 시험용 DB 에 풀기 (backup 서버의 파일을 mariadb-pr 로 복사한 뒤)
[admina@mariadb-pr ~]$ gunzip -c /tmp/mariadb.sql.gz | sudo mariadb gamenuri_restore_test

# 복구 결과 확인: 테이블 수가 28개, 주요 테이블 행 수가 운영과 비슷한지
[admina@mariadb-pr ~]$ sudo mariadb gamenuri_restore_test -e "SHOW TABLES; SELECT COUNT(*) FROM games;"

# 시험용 DB 지우기 (⚠ 되돌릴 수 없음 — 이름이 gamenuri_restore_test 인지 다시 읽는다)
[admina@mariadb-pr ~]$ sudo mariadb -e "DROP DATABASE gamenuri_restore_test"
```
> <- `DROP DATABASE` 는 **시험용 이름일 때만** 실행합니다. 운영 DB 이름(`gamenuri`)이면 즉시 중단하고 팀장에게 알립니다.
> <- 덤프를 `gamenuri_restore_test` 에 풀 때 덤프 안의 `USE gamenuri` 구문이 있으면 운영 DB로 들어갈 수 있습니다. 덤프를 연 뒤 `grep -m3 -n "USE\|CREATE DATABASE" ...` 로 먼저 확인합니다(⚠ 미확인: 이 덤프에 그 구문이 들어 있는지).

```
# (MongoDB) 시험용 DB 이름으로 풀기: 원본 DB 이름을 다른 이름으로 바꿔서 복구
[admina@backup ~]$ mongorestore --uri "<MONGO_URI의 호스트 부분, 관리자 계정>" --gzip --archive=/BACKUP/<날짜>/mongo.archive.gz --nsFrom 'gamenuri_raw.*' --nsTo 'gamenuri_restore_test.*'
```
> <- `--nsFrom/--nsTo` 로 이름을 바꿔 운영 `gamenuri_raw` 를 건드리지 않게 합니다. 복구에는 `backup`(읽기 전용) 계정이 아니라 **쓰기 권한이 있는 계정**이 필요합니다. 비밀번호는 입력창으로 받습니다.
> <- 시험이 끝나면 `gamenuri_restore_test` DB 를 지웁니다(`db.getSiblingDB("gamenuri_restore_test").dropDatabase()`, `⚠ 되돌릴 수 없음`, 이름 확인 후).
> <- 실제 사고 때는 **날아간 테이블·컬렉션만** 옮깁니다. 덤프 전체를 운영 DB에 바로 돌리면 멀쩡한 데이터까지 덤프 시점으로 되감깁니다.

## 9. 점검 (매주 한 번)
```
# 최근 7일 폴더가 모두 있는지, 크기가 크게 줄지 않았는지
[admina@backup ~]$ ls -lh /BACKUP/*/

# 디스크 여유
[admina@backup ~]$ df -h /BACKUP

# 최근 로그
[admina@backup ~]$ tail -20 /var/log/game-nuri-backup.log
```

## 10. 남은 일
- [ ] backup 서버의 cron 등록과 첫 자동 실행 확인
- [ ] `backup` DB 계정(MariaDB·MongoDB) 생성 확인
- [ ] 복구 시험 실행과 결과 기록
- [ ] 발표 전날 VM **스냅샷**(VirtualBox)과 백업 파일을 PC 밖에 보관하는 방법 검토
