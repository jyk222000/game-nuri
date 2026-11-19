# 아키텍처

## 구성
- PC 2대 (각 32GB), VirtualBox VM 17대, 브리지 네트워크, 스위치로 연결
- 공인 IP 2개: `0.222` → Proxy·수집 서버 (서비스 입구), `0.223` → 모니터링 (관리용 입구)

| PC | VM | 역할 |
|---|---|---|
| PC-1 | Proxy·수집 서버 | HAProxy(→Frontend 1·2), 수집기, 내부망 NAT 게이트웨이 |
| PC-1 | Frontend 1·2 | 웹 화면, `/api`를 짝 Backend로 전달 |
| PC-1 | Backend 1·2 | FastAPI, 클릭스트림 발행 |
| PC-1 | Kafka 1~3 | 브로커 + 정제 프로그램 + Kafka Connect |
| PC-1 | 백업 서버 | MariaDB·MongoDB 매일 덤프, 7일 보관 |
| PC-2 | MariaDB Primary · Replica | 정제값, 사용자, 알림 |
| PC-2 | MongoDB ×3 (P-S-S) | 원본 JSON, 리뷰 |
| PC-2 | ELK | 게임 검색, 클릭스트림 로그, Monstache(MongoDB→ES 동기화) |
| PC-2 | Valkey | 공용 캐시, 세션, 알림 중복 방지 |
| PC-2 | 모니터링 | Prometheus, Grafana → Slack, 점프 서버 |

## 데이터 흐름
1. 수집: 수집기 → `raw.price`, `raw.console`, `raw.steam`, `raw.igdb`
2. 정제: refiner가 raw.* 소비 → 중복 제거·원화 환산·게임 ID 통합 → `refined.*`
3. 저장: Kafka Connect가 refined.* → MariaDB, raw.* → MongoDB, refined.games → MongoDB `games`, clickstream → ES
3-1. 동기화: Monstache가 MongoDB `games` 변경을 감지해 ES `games` 인덱스(한글 nori 분석기)에 반영
4. 서비스: 사용자 → Proxy → FE → BE → MariaDB(Replica 읽기) / ES / Valkey

5. 외부 접속: DDNS 도메인 → 0.222 → HAProxy(HTTPS, Let's Encrypt) — 구글 로그인에 필요
6. 모니터링: 모든 VM node_exporter + Backend API 계측 → Prometheus → Grafana(인기 API 순위) → Slack

구조도 원본: `docs/diagrams/gamenuri-infra-architecture.drawio`
