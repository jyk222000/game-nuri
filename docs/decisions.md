# 결정 기록
형식: `YYYY-MM-DD | 결정 | 이유`

- 2026-11-18 | 콘솔 가격은 다나와 크롤링 | 콘솔 스토어 직접 크롤링은 약관상 어려움
- 2026-11-18 | 게임 정보는 IGDB, 기준 게임 ID = IGDB ID | 스토어별 외부 ID를 제공해 ID 통합이 쉬움
- 2026-11-18 | 정제는 Kafka 쪽 refiner, DB 적재는 Kafka Connect | Backend는 API만 담당 (강사 피드백)
- 2026-11-18 | Proxy → FE1·FE2 → BE1·BE2 (짝 연결) | FE-BE 연결 구조 명확화 (강사 피드백)
- 2026-11-18 | MariaDB Primary-Replica, Valkey 별도 VM, 백업 서버 PC-1 | 가용성 · 공유 상태 · 다른 PC에 백업
