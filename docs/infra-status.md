# 인프라 현황 (2026-11-28 갱신, 최초 11/22)

> 11/22 이후 변경은 각 담당의 구축 기록(`infra/*/README.md`, `infra/workbook/07-작업내역.md`)과 `docs/decisions.md`를 근거로 반영했다.
> 이 문서를 위해 서버를 다시 확인하지는 않았다. 근거가 없는 항목은 **미확인**이다.
> 실제 VM 출력으로 확인한 값이다. 확인하지 못한 항목은 **미확인**으로 적었다. 비밀번호는 적지 않는다.
> 호스트 이름·IP·포트는 `docs/network.md`가 기준이다. DB 설치 내용은 `infra/mariadb/`, `infra/mongodb/`.

## 완료
| 작업 | 대상 | 내용 | 날짜 |
|---|---|---|---|
| 네트워크 | 17대 | 게이트웨이 2대(proxy, monitoring) NAT, 내부 VM 기본 경로, 양쪽 PC 인터넷 | 11/20 |
| 게이트웨이 iptables | proxy, monitoring | FORWARD(ESTABLISHED·RELATED, 내망→외부, 상대망→내망)·MASQUERADE 확인, `service iptables save`로 저장 | 11/22 |
| hostname · `/etc/hosts` | 17대 | 소문자 이름으로 통일, 17줄 등록 | 11/20 |
| 공통 패키지 · 시간 | 17대 | chrony·vim·git 등, 타임존 Asia/Seoul, `vm.swappiness=1` | 11/20 |
| 팀 계정 · 공용 폴더 | 17대 | admina~admind (wheel + gamenuri), `/opt/game-nuri` | 11/20 |
| **MariaDB** | mariadb-pr, mariadb-re | 10.11.18 Primary→Replica 복제, DB `gamenuri`, 테이블 28개(이고은, 11/22), 복제 재확인 | 11/20, 11/22 |
| **MongoDB** | mongodb-pr, mongo-se1·se2 | 8.0.38 복제 셋 `rs0`, 장애 전환·재부팅 테스트 통과, 11/22 재확인 | 11/20 |
| **Kafka** | kafka1~3, backup, monitoring | 3.8.0 KRaft, 브로커 3 + 투표 5, 토픽 10개, Connect 3대 (남현식) | 11/21 |
| **도메인 · HTTPS** | proxy | `gamenuri.store` → 192.168.0.222, Let's Encrypt(DNS-01, 만료 2027-02-18), HAProxy 443 (한예찬) | 11/20 |
| **Valkey** | valkey | 8.1, `maxmemory 256mb`·`allkeys-lru`, 저장 끔, 인증 사용. PackageKit 캐시 정리로 `/` 여유 확보(재설치 안 함) | 11/22 |
| 방화벽 정리 | 내부 VM 10대 | frontend1·2, backend1·2, elk, mariadb-pr·re, mongodb-pr, mongo-se1·2 firewalld 끔 | 11/22 |
| 방화벽 정리(나머지) | 내부 VM 전부 | 남은 kafka1~3, backup, valkey까지 firewalld 꺼짐 확인(monitoring은 masked) | 11/25 |
| **ES · Kibana · Monstache** | elk | ES 8.19.25, Monstache 6.8.0(games·reviews 동기화), Kibana. 11/27 `game_aliases` 인덱스 추가(Mongo Sink 연결), Monstache `resume=false` (남현식) | 11/23, 11/27 |
| **수집기** | proxy | 타이머 8종 가동, 게임 1,000개 수집 (`docs/collector-test/first-run-2026-11-23.md`) (한예찬) | 11/23 |
| **Backend · Frontend** | backend1·2, frontend1·2 | backend1 11/23~24 배포, backend2·frontend2 11/26 배포(`/api/health` 정상, 두 서버 같은 커밋·요청 분산). 알림 메일 타이머는 backend1만 (`infra/backend/README.md`) | 11/24, 11/26 |
| **게임 검색 ES 연동** | backend1 | `SEARCH_BACKEND=es` 스위치와 MariaDB 대체 경로, backend1에서 확인(11/27). backend2 적용·확인은 미확인 (`docs/es-search.md`) | 11/27 |
| **백업** | backup | 매일 03:00 자동 실행 3일 연속(11/25~27), MariaDB 복구 10.5초·MongoDB 복구 48.8초 시험, 복제 지연 0초 (`infra/workbook/06-backup.md`) | 11/25~27 |
| Kibana LAN 접속 | proxy → elk | `http://192.168.0.222:5601`, clickstream에 게임·사용자 이름 붙이기 (`docs/decisions.md` 11/26) (남현식) | 11/26 |

## 미해결
| # | 문제 | 조치 |
|---|---|---|
| 1 | ~~firewalld가 남은 VM: kafka1~3, backup, valkey~~ | 해결 11/25: 내부 VM 전부 꺼짐 확인 |
| 2 | dnf update 미적용 VM (PC-2 다수, monitoring) | 발표 후로 미뤄도 됨 |
| 3 | ~~elk 재부팅 필요 (새 커널 미적용)~~ | 해결 11/23: 커널 6.12.0-264 적용, 부팅 모드 multi-user (남현식) |
| 4 | ~~Kafka Connect ES Sink~~ | 해결 11/23: ES 8.19.25 + Confluent ES Sink 16.0.1, `es-sink-clickstream` RUNNING (남현식) |
| 5 | 임시 `/etc/sudoers.d/admin`(NOPASSWD) 17대에 남음 | 팀장 확인 후 삭제 |
| 6 | SSH 호스트 키·machine-id 중복 의심 (같은 이미지 복제) | 17대 점검, MongoDB 3대는 호스트 키 재생성 완료 |
| 7 | 인증서 수동 갱신 (`--manual`) | 2027-02-18 전 재발급 (`docs/network.md`) |
| 8 | 내부 VM DNS 값이 문서와 다름 | 통일 결정 |
| 9 | ~~`backup.sh` 경로가 `/backup`, 실제 디스크는 `/BACKUP`~~ | 해결 11/23: `/BACKUP` 마운트 확인 후 백업 (`infra/backup/backup.sh`) |
| 10 | 백업이 같은 구성(VM) 안에만 있음, PC 밖 보관 없음 | 발표 전 보관 방법 결정 (`infra/workbook/06-backup.md`) |
| 11 | 장애 전환 시간(Frontend·MongoDB PRIMARY) 측정 전 | 리허설에서 측정 |

## DB 남은 일 (11/28 기준)
- MariaDB: `erd.sql` 29개 테이블(`game_review_stats` 추가)·서비스 계정(`gamenuri_app`, 백업용)은 반영됨. 남은 것: 계정 분리·GTID 복제 전환(발표 후)
- MongoDB: `raw_*` 컬렉션 `ingested_at` TTL 14일 적용(11/25), Monstache 계정 권한 확인 완료. 남은 것: TTL이 실제로 오래된 문서를 지우는지 14일 뒤 확인

## 일정 (11/22 회의 기준)
| 날짜 | 작업 | 담당 | 상태 |
|---|---|---|---|
| 11/20 | 네트워크·계정, MariaDB·MongoDB, 도메인·HTTPS | 김준영, 한예찬 | 완료 |
| 11/21 | Kafka KRaft 클러스터, 토픽, Connect | 남현식 | 완료 |
| 11/22 | Valkey, 테이블 28개, 방화벽 정리(10대), Frontend 목업 | 김준영, 이고은, 한예찬 | 완료 |
| 11/23 | 남은 firewalld 5대, elk 재부팅 → ES·Kibana·Monstache, 게임 100개 흐름 검증 | 남현식, 김준영 | ES·Kibana·Monstache 완료 (games 1000·reviews 451,368건 ES 동기화) |
| 11/23 | proxy 수집기 설치·첫 실행, 타이머 8개 가동, 게임 1,000개 수집 (`docs/collector-test/first-run-2026-11-23.md`) | 한예찬 | 완료 (11/24 아침 8종 정상, `--failed` 0건) |
| 11/24 | Backend·Frontend 배포 (수집기 타이머·게임 1,000개 수집은 11/23에 앞당겨 완료) | 김준영, 한예찬 | 완료 (backend1·frontend1) |
| 11/25 | Prometheus·Grafana, 백업 cron·복구 시험, 게임 1,000개, 구축 동결 | 남현식, 김준영 | 백업 cron·복구 시험 완료(11/25~27). Prometheus·Grafana는 남현식 문서 참고(`infra/monitoring/`), 이 문서에서는 미확인 |
| 11/26 | backend2·frontend2 배포, Kibana LAN 접속 | 김준영, 한예찬, 남현식 | 완료 |
| 11/27 | 게임 검색 ES 연동(별칭 인덱스, 스위치), 백업 RPO·RTO 측정 | 김준영, 남현식 | 완료 (backend2 적용 미확인) |
| 11/26~27 | 분석 8개, Locust 부하, 장애 시나리오 | 전체 | 분석: `analysis/` 참고. Locust 부하·장애 시나리오 결과는 이 문서에서 미확인 |
| 11/29 | 최종 스냅샷, 리허설 | 전체 | 예정 |
