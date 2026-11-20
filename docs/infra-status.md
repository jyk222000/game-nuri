# 인프라 현황 (2026-11-21 01시 기준)

> 실제 VM 출력으로 확인한 값이다. 확인하지 못한 항목은 **미확인**으로 적었다. 비밀번호는 적지 않는다.
> 호스트 이름·IP·포트는 `docs/network.md`가 기준이다. DB 설치 내용은 `infra/mariadb/`, `infra/mongodb/`.

## 완료
| 작업 | 대상 | 내용 | 날짜 |
|---|---|---|---|
| 네트워크 | 17대 | 게이트웨이 2대(proxy, monitoring) NAT, 내부 VM 기본 경로, 양쪽 PC 인터넷 | 11/20 |
| hostname · `/etc/hosts` | 17대 | 소문자 이름으로 통일, 17줄 등록 | 11/20 |
| 공통 패키지 · 시간 | 17대 | chrony·vim·git 등, 타임존 Asia/Seoul, `vm.swappiness=1` | 11/20 |
| 팀 계정 · 공용 폴더 | 17대 | admina~admind (wheel + gamenuri), `/opt/game-nuri` | 11/20 |
| Kafka VM 인계 | kafka1~3 | 남현식에게 인계, 클러스터 구축 진행 중 | 11/20 |
| **MariaDB** | mariadb-pr, mariadb-re | 10.11.18 Primary→Replica 복제, DB `gamenuri`, 방화벽 3306 (10.0.0.0/16) | 11/20 |
| **MongoDB** | mongodb-pr, mongo-se1·se2 | 8.0.38 복제 셋 `rs0`, 장애 전환·재부팅 테스트 통과, 방화벽 27017 | 11/20 |
| **도메인 · HTTPS** | proxy | `gamenuri.store` → 192.168.0.222, Let's Encrypt(DNS-01, 만료 2027-02-18), HAProxy 443 (한예찬, PR #13·#14) | 11/20 |
| Valkey RAM | valkey | 2GB → 1GB | 11/20 |

## 미해결
| # | 문제 | 조치 |
|---|---|---|
| 1 | Valkey `/` 97% (GUI 설치됨) | Minimal 재설치(권장) 또는 GUI 패키지 37개 제거. `--skip-broken`, `--nobest` 금지 |
| 2 | dnf update 미적용 7대 (PC-2 6대 `/` 공간 부족 + valkey) | 발표 후로 미뤄도 됨 |
| 3 | elk 재부팅 필요 (새 커널 미적용) | ES 설치 전 재부팅 |
| 4 | 게이트웨이 FORWARD 규칙·방화벽 저장 여부 미확인 | `sudo iptables -S FORWARD`, `systemctl is-enabled iptables` |
| 5 | 임시 `/etc/sudoers.d/admin`(NOPASSWD) 17대에 남음 | 팀장 확인 후 삭제 |
| 6 | SSH 호스트 키·machine-id 중복 의심 (같은 이미지 복제) | 17대 점검, MongoDB 3대는 호스트 키 재생성 완료 |
| 7 | 인증서 수동 갱신 (`--manual`) | 2027-02-18 전 재발급 (`docs/network.md`) |
| 8 | 내부 VM DNS 값이 문서와 다름 | 통일 결정 |

## DB 남은 일
- MariaDB: ERD 적용(이고은), `/tmp/full.sql` 삭제, 스냅샷, GTID 전환, 계정 분리
- MongoDB: 스냅샷, 컬렉션·TTL 확정, Monstache 권한 확인

## 일정
| 날짜 | 작업 | 담당 | 상태 |
|---|---|---|---|
| 11/20 | 네트워크·계정, Kafka VM 인계 | 김준영 | 완료 |
| 11/20 | MariaDB·MongoDB (계획보다 하루 앞당김) | 김준영 | 완료 |
| 11/20 | 도메인·HTTPS (계획 11/26~27) | 한예찬 | 완료 |
| 11/20~ | Kafka KRaft 클러스터, 토픽 | 남현식 | 진행 중 |
| 11/21 | ERD 적용, 정제 로직 | 이고은 | 정규화 완료 |
| 11/22 | Valkey, Frontend 디자인 목업 | 김준영, 한예찬 | 예정 |
| 11/23 | elk 재부팅 → Elasticsearch·Kibana·Monstache, Kafka Connect | 김준영, 남현식 | 예정 |
| 11/24 | Backend·Frontend 배포, 수집기 타이머 | 미정, 한예찬 | 예정 |
| 11/25 | Prometheus·Grafana, 백업 cron | 김준영 | 예정 |
| 11/26 | 게임 300개로 전체 흐름 검증 | 전체 | 예정 |
| 11/27~28 | Locust 부하, 장애 시나리오 | 전체 | 예정 |
| 11/29 | 최종 스냅샷, 리허설 | 전체 | 예정 |
