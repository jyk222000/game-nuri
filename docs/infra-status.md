# 인프라 현황 (2026-11-22 기준)

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

## 미해결
| # | 문제 | 조치 |
|---|---|---|
| 1 | firewalld가 남은 VM: kafka1~3, backup, valkey | 남현식과 한 대씩 끄고 Kafka 투표 5개·Connect·Valkey PING 확인 |
| 2 | dnf update 미적용 VM (PC-2 다수, monitoring) | 발표 후로 미뤄도 됨 |
| 3 | elk 재부팅 필요 (새 커널 미적용) | ES 설치 전 재부팅 (남현식) |
| 4 | Kafka Connect ES Sink | ES 버전에 따라 커넥터가 달라 보류. ES 설치 후 결정 (남현식) |
| 5 | 임시 `/etc/sudoers.d/admin`(NOPASSWD) 17대에 남음 | 팀장 확인 후 삭제 |
| 6 | SSH 호스트 키·machine-id 중복 의심 (같은 이미지 복제) | 17대 점검, MongoDB 3대는 호스트 키 재생성 완료 |
| 7 | 인증서 수동 갱신 (`--manual`) | 2027-02-18 전 재발급 (`docs/network.md`) |
| 8 | 내부 VM DNS 값이 문서와 다름 | 통일 결정 |
| 9 | `backup.sh` 경로가 `/backup`, 실제 디스크는 `/BACKUP`(sda3 80G) | Backend 작업에서 수정 PR |

## DB 남은 일
- MariaDB(이고은): `erd.sql`을 실제 28개 테이블로 갱신(contracts PR), 가격 키 플랫폼·상태 결정, 서비스 계정(`gamenuri_app`, 백업용) 생성
- MongoDB(김준영): 스냅샷, 컬렉션·TTL 확정, Monstache 계정 권한 확인(남현식과)

## 일정 (11/22 회의 기준)
| 날짜 | 작업 | 담당 | 상태 |
|---|---|---|---|
| 11/20 | 네트워크·계정, MariaDB·MongoDB, 도메인·HTTPS | 김준영, 한예찬 | 완료 |
| 11/21 | Kafka KRaft 클러스터, 토픽, Connect | 남현식 | 완료 |
| 11/22 | Valkey, 테이블 28개, 방화벽 정리(10대), Frontend 목업 | 김준영, 이고은, 한예찬 | 완료 |
| 11/23 | 남은 firewalld 5대, elk 재부팅 → ES·Kibana·Monstache, 게임 100개 흐름 검증 | 남현식, 김준영 | 예정 |
| 11/24 | Backend·Frontend 배포, 수집기 타이머, 게임 300개 | 김준영, 한예찬 | 예정 |
| 11/25 | Prometheus·Grafana, 백업 cron·복구 시험, 게임 1,000개, 구축 동결 | 남현식, 김준영 | 예정 |
| 11/26~27 | 분석 8개, Locust 부하, 장애 시나리오 | 전체 | 예정 |
| 11/29 | 최종 스냅샷, 리허설 | 전체 | 예정 |
