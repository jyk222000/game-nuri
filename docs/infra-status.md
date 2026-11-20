# 인프라 현황 (2026-11-20 16:30 기준)

> 실제 VM 출력으로 확인한 값이다. 확인하지 못한 항목은 **미확인**으로 적었다. 비밀번호는 적지 않는다.
> 호스트 이름·IP·포트는 `docs/network.md`가 기준이다.

## 완료
| 작업 | 대상 | 내용 |
|---|---|---|
| 네트워크 | 17대 | 게이트웨이 2대(proxy, monitoring) NAT, 내부 VM 기본 경로, 양쪽 PC 인터넷 |
| hostname · `/etc/hosts` | 17대 | 소문자 이름으로 통일, 17줄 등록 (백업 `/etc/hosts.bak.날짜`) |
| 공통 패키지 | 17대 | chrony, vim, git, tar, wget, net-tools, bind-utils, policycoreutils-python-utils |
| 시간 · 커널 | 17대 | chronyd 활성, 타임존 Asia/Seoul, `vm.swappiness=1` |
| dnf update | 10대 | 9대 성공 + proxy는 이미 최신 |
| 팀 계정 | 17대 | admina~admind (wheel + gamenuri), 생성 확인 11/20 16:08 |
| 공용 폴더 | 17대 | `/opt/game-nuri` (root:gamenuri, 2775) |
| Valkey | valkey | IPv4 DNS 복구, 기본 부팅 `multi-user.target`(다음 부팅부터), RAM 1GB로 변경 |

## 미해결
| # | 문제 | 조치 |
|---|---|---|
| 1 | Valkey `/` 97% (8.0G 중 290MB 남음, GUI 설치됨) | Minimal 재설치(권장) 또는 GUI 패키지 37개 제거(시뮬레이션 515MB, 미실행). `dnf group remove "Server with GUI"`는 dnf·sudo까지 지우려 해서 거부됨. `--skip-broken`, `--nobest` 금지 |
| 2 | dnf update 미적용 7대: monitoring, mariadb-pr, mariadb-re, mongodb-pr, mongo-se1, mongo-se2(`/` 공간 부족) + valkey | GUI 설치 여부 확인(`systemctl get-default`). 업데이트는 발표 후로 미뤄도 됨 |
| 3 | 위 7대 `/` 공간이 작음 | DB 데이터·로그는 `/DATA`에. `df -h /DATA` 용량 미확인 |
| 4 | elk 재부팅 필요 (실행 커널 6.12.0-124, 설치 커널 6.12.0-264) | ES 설치 전 재부팅 |
| 5 | FORWARD 규칙 미확인 (Proxy 저장 규칙에 ESTABLISHED 줄 없음, 기본 정책 ACCEPT. monitoring은 못 봄) | `sudo iptables -S FORWARD`, `systemctl is-enabled iptables` 확인 후 `infra/network/gateway.sh` 기준으로 맞춤 |
| 6 | 내부 VM DNS가 문서와 다름 (실제 203.248.252.2·164.124.101.2) | 한쪽으로 통일 결정 |
| 7 | 임시 `/etc/sudoers.d/admin`(NOPASSWD)이 17대에 남아 있음 | 팀 계정 비밀번호 확인 후 삭제 (팀장 확인 후에만) |
| 8 | 팀 계정 비밀번호 설정 미확인 | `sudo passwd adminX` → `su - adminb -c 'sudo whoami'` |

## 일정
| 날짜 | 작업 | 담당 |
|---|---|---|
| 11/20 (금) | 계정 비밀번호, Kafka 3대 인계 | 김준영 → 남현식 |
| 11/20~21 | Kafka KRaft 3노드, 토픽 생성 | 남현식 |
| 11/21 (토) | MariaDB Primary·Replica (`/DATA/mysql`, SELinux), ERD 적용 | 김준영, 이고은 |
| 11/22 (일) | MongoDB 레플리카셋 3대, Valkey | 김준영 |
| 11/23 (월) | elk 재부팅 → Elasticsearch·Kibana·Monstache, Kafka Connect | 김준영, 남현식 |
| 11/24 (화) | Backend·Frontend·HAProxy, 수집기 타이머 | 미정, 한예찬 |
| 11/25 (수) | Prometheus·Grafana, node_exporter, 백업 cron | 김준영 |
| 11/26 (목) | 게임 300개로 전체 흐름 검증 | 전체 |
| 11/26~28 | DDNS·HTTPS, Locust 부하, 장애 시나리오 | 전체 |
| 11/29 (일) | 최종 스냅샷, 리허설 | 전체 |

## 팀장 확인 필요
정적 경로, 내부 VM 어댑터 1개 구성, VM별 역할·담당(계획값), MongoDB·ES 디스크 필요량(약 5GB, 추정), 리뷰 최초 적재 시간(약 3.8시간, 추정).
