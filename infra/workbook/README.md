# 겜누리 구축 워크북 (김준영 파트: 인프라 · MariaDB · Valkey · MongoDB · Backend · 백업)

처음 보는 사람이 **이 문서만 보고 같은 서버를 다시 만들 수 있게** 쓴 워크북입니다.
서버에서 실제로 실행한 명령은 각 파트의 기존 기록(`infra/*/README.md`)과 레포 파일(`infra/`, `backend/`)을 근거로 했고,
**서버에서 확인하지 못한 것은 `⚠ 미확인`으로 표시**했습니다. 비밀번호·키·API 키 값은 어디에도 적지 않습니다.

## 표기 방법 (모든 파트 공통)
```
# 회색 줄 : 바로 아래 명령이 하는 일
[admina@서버이름 ~]$ 실제로 입력하는 명령
> 설정 파일 내용, 명령 결과처럼 직접 입력하지 않는 줄
```
> <- 인용 줄은 성공 기준, 이유, 주의할 점

- `<꺾쇠>` 로 표시한 값은 각자 환경에 맞게 **바꿔서** 입력합니다. 꺾쇠를 그대로 붙여 넣으면 셸이 오류를 냅니다.
- 명령 앞의 `[admina@서버이름 ~]$` 에서 **서버 이름을 꼭 확인**합니다. 다른 VM에 설치한 적이 있습니다(MariaDB를 mongodb-pr에 설치, 제거함).
  명령을 실행하기 전에 항상 `hostname`으로 확인합니다.
- `sudo` 가 앞에 붙은 명령은 팀 계정(`admina`~`admind`)으로 접속해서 실행합니다.
- **삭제·초기화 명령**(`DROP`, `TRUNCATE`, `rm -rf`, `deleteMany`, 토픽 삭제)은 이 워크북에서 `⚠ 되돌릴 수 없음` 으로 표시하고, 실행 전에 팀장 확인을 받습니다.

## 목차 (진행 순서)
| 순서 | 문서 | 서버 | 내용 |
|---|---|---|---|
| 1 | [01-공통준비.md](01-공통준비.md) | 17대 전체 | 네트워크 구조, 호스트 이름, 계정, SSH, 시간·패키지, 방화벽 정책 |
| 2 | [02-mariadb.md](02-mariadb.md) | mariadb-pr, mariadb-re | MariaDB 10.11 Primary → Replica 복제, 계정 |
| 3 | [03-valkey.md](03-valkey.md) | valkey | 캐시·세션·실시간 검색어 저장소 |
| 4 | [04-mongodb.md](04-mongodb.md) | mongodb-pr, mongo-se1, mongo-se2 | MongoDB 8.0 복제 셋 `rs0`, 컬렉션·인덱스·TTL, 정리 작업 |
| 5 | [05-backend.md](05-backend.md) | backend1 (backend2) | FastAPI 설치, 환경 파일, systemd, 구글 로그인, AI, 알림 메일, 배포 |
| 6 | [06-backup.md](06-backup.md) | backup | MariaDB·MongoDB 매일 백업, 복구 시험 |
| 7 | [07-작업내역.md](07-작업내역.md) | - | 날짜별 총 작업 내용, 결정, 겪은 문제, 남은 일 |

> <- 순서의 이유: 모든 서버가 호스트 이름과 고정 IP로 서로를 찾으므로 1번이 먼저입니다. Backend(5)는 MariaDB(2)·Valkey(3)·ES(남현식 담당)가 있어야 뜨고,
> 백업(6)은 MariaDB·MongoDB의 읽기 전용 계정이 있어야 합니다.

## 이 워크북이 다루지 않는 것 (다른 담당)
| 담당 | 영역 | 문서 위치 |
|---|---|---|
| 남현식 | Kafka·Kafka Connect, Elasticsearch·Kibana·Monstache, Prometheus·Grafana | `infra/kafka/`, `infra/elk/`, `infra/monstache/`, `infra/monitoring/`, `pipeline/connect/` |
| 이고은 | MariaDB 테이블(ERD) 설계, 정제 프로그램 | `docs/contracts/erd.sql`, `pipeline/refiner/` |
| 한예찬 | 수집기, HAProxy·도메인·HTTPS, Frontend, 구글 로그인·AI 서비스 코드 | `collector/`, `infra/haproxy/`, `infra/frontend/`, `infra/collector/` |

## 전체 구조 한눈에
```
사용자 → proxy(HAProxy, 192.168.0.222) → frontend1·2(nginx) → backend1·2(FastAPI :8000)
                                                         ├─ mariadb-pr(쓰기) / mariadb-re(읽기)
                                                         ├─ valkey(캐시·세션)
                                                         ├─ elk(Elasticsearch, 검색·클릭스트림)
                                                         └─ kafka1~3(clickstream 발행)
수집기(proxy) → Kafka raw.* → 정제 → Kafka refined.* → Kafka Connect → MariaDB / MongoDB
MongoDB(games·reviews) → Monstache → Elasticsearch
backup 서버: 매일 03:00 MariaDB·MongoDB를 읽어 /BACKUP에 7일 보관
```
- 기준 문서: `docs/network.md`(IP·포트), `docs/infra-status.md`(현황), `docs/decisions.md`(결정 기록), `docs/contracts/`(약속).
