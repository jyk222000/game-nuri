# 결정 기록
형식: `YYYY-MM-DD | 결정 | 이유`

- 2026-11-20 | 도메인은 `gamenuri.store`(가비아, 구입 완료), 공개 DNS A 레코드를 proxy 사설 IP 192.168.0.222로 지정, 인증서는 Let's Encrypt DNS-01 | 포트포워딩 불가·강의실 LAN에서만 접속, 구글 OAuth는 실제 도메인+HTTPS 필요
- 2026-11-20 | OS는 Rocky Linux 10, 내부망 10.0.1.0/24(PC-1)·10.0.2.0/24(PC-2), 게이트웨이 proxy·monitoring | 실제 구축 환경 반영 (docs/network.md)
- 2026-11-20 | VM hostname은 17대에 적용된 이름(frontend1, backend1, monitoring, mariadb-pr/re, mongodb-pr, mongo-se1/2)으로 확정 | 이미 17대 hostname·/etc/hosts에 적용됨, VM을 다시 바꾸는 것보다 문서 수정이 적음
- 2026-11-18 | 콘솔 가격은 다나와 크롤링 | 콘솔 스토어 직접 크롤링은 약관상 어려움
- 2026-11-18 | 게임 정보는 IGDB, 기준 게임 ID = IGDB ID | 스토어별 외부 ID를 제공해 ID 통합이 쉬움
- 2026-11-18 | 정제는 Kafka 쪽 refiner, DB 적재는 Kafka Connect | Backend는 API만 담당 (강사 피드백)
- 2026-11-18 | Proxy → FE1·FE2 → BE1·BE2 (짝 연결) | FE-BE 연결 구조 명확화 (강사 피드백)
- 2026-11-19 | 서비스 기능 10개 · API 38개 · 과제 8개로 확정 | 팀 기능 정리 PDF + 강사 요구사항 (docs/features.md)
- 2026-11-19 | 클리어 시간은 IGDB game_time_to_beats | HowLongToBeat 공식 API 없음
- 2026-11-19 | 리뷰 요약 = ES 키워드 추출 후 키워드만 AI에 전송 | AI 비용·속도 절감, ES 활용 근거
- 2026-11-19 | PC 사양 = Steam 최소·권장 + 사용자 선택 입력, AI 비교 결과는 캐시 | 같은 입력에 같은 결과
- 2026-11-19 | 본 수집 전 게임 10개로 전체 흐름 테스트 (11/20~11/23) | 문제 위치를 단계별로 분리 (docs/test-plan.md)
- 2026-11-19 | 컨테이너는 이번에 쓰지 않음, VM + systemd | 데이터 처리 과정 학습이 주목적 (강사 확인)
- 2026-11-19 | Monstache로 MongoDB games → ES 동기화 | 강사 요구사항, 저장소 간 동기화 학습
- 2026-11-19 | 회원가입은 구글 로그인, DDNS 도메인 + HTTPS | 구글 OAuth는 IP 주소·HTTP redirect 불가
- 2026-11-18 | MariaDB Primary-Replica, Valkey 별도 VM, 백업 서버 PC-1 | 가용성 · 공유 상태 · 다른 PC에 백업
