# Backend API 명세 (기능 명세서)

- **38개** (요구사항: 30개 이상). 기능 단위로 센다. 기능 명세는 `docs/features.md`.
- 실제 동작 명세는 FastAPI가 만드는 `/docs`(Swagger)와 일치시킨다. 경로는 구현하며 확정.
- 기본 경로 `/api`, JSON, 키 `snake_case`, 시간 UTC ISO 8601, 금액 `price_krw`(원화 정수)
- 인증: 구글 로그인 후 세션 쿠키 (세션은 Valkey). ✓ = 로그인 필요
- 오류: `{"error": {"code": "NOT_FOUND", "message": "게임을 찾을 수 없습니다"}}`
- 목록: `{"items": [...], "total": 123, "page": 1, "size": 20}`

| # | 분류 | API | 경로 (초안) | 기능 | 로그인 |
|---|---|---|---|---|---|
| 1 | 인증 | 구글 로그인 | `GET /api/auth/google/login, /api/auth/google/callback` | ⑧ |  |
| 2 | 인증 | 토큰 갱신·로그아웃 | `POST /api/auth/refresh, /api/auth/logout` | ⑧ | ✓ |
| 3 | 인증 | 내 프로필 | `GET·PATCH /api/me` | ⑧ | ✓ |
| 4 | 인증 | Steam ID 연동 | `PUT /api/me/steam` | ④ | ✓ |
| 5 | 게임 | 검색 (한글 부분·오타) | `GET /api/games?q=&platform=&genre=` | 공통 |  |
| 6 | 게임 | 자동완성 | `GET /api/games/autocomplete?q=` | 공통 |  |
| 7 | 게임 | 상세 | `GET /api/games/{game_id}` | 공통 |  |
| 8 | 게임 | 장르·태그 필터 | `GET /api/genres, /api/tags` | 공통 |  |
| 9 | 게임 | 인기 게임 목록 | `GET /api/games/popular` | 공통 |  |
| 10 | 가격 | 스토어별 비교 | `GET /api/games/{game_id}/prices` | ① |  |
| 11 | 가격 | 가격 이력 | `GET /api/games/{game_id}/history?days=180` | ① ② |  |
| 12 | 가격 | 역대 최저가 | `GET /api/games/{game_id}/lowest` | ① ② |  |
| 13 | 가격 | 할인 중 목록 | `GET /api/games/deals` | ① |  |
| 14 | 가격 | 원화 환산 기준(환율) | `GET /api/exchange-rates` | ① |  |
| 15 | 구매 타이밍 | 지금 살지 판단 | `GET /api/games/{game_id}/timing` | ② |  |
| 16 | 구매 타이밍 | 할인 예측 | `GET /api/games/{game_id}/prediction` | ② |  |
| 17 | 찜·알림 | 찜 추가·삭제 | `POST·DELETE /api/me/wishlist` | ③ | ✓ |
| 18 | 찜·알림 | 찜 목록 | `GET /api/me/wishlist` | ③ | ✓ |
| 19 | 찜·알림 | 목표가 설정·수정·삭제 | `POST·PATCH·DELETE /api/me/alerts` | ③ | ✓ |
| 20 | 찜·알림 | 목표가 목록 | `GET /api/me/alerts` | ③ | ✓ |
| 21 | 찜·알림 | 알림 내역 | `GET /api/me/alerts/logs` | ③ | ✓ |
| 22 | 찜·알림 | 메일 수신 설정 | `PUT /api/me/notifications` | ③ | ✓ |
| 23 | 추천 | 플레이타임 기반 추천 | `GET /api/me/recommendations` | ④ | ✓ |
| 24 | 추천 | 내 취향 프로필 | `GET /api/me/taste` | ④ | ✓ |
| 25 | 추천 | 짧게 끝낼 게임 추천 | `GET /api/games/short` | ④ |  |
| 26 | 리뷰 | 리뷰 목록 | `GET /api/games/{game_id}/reviews` | ⑤ |  |
| 27 | 리뷰 | 리뷰 요약 (ES 키워드 + AI) | `GET /api/games/{game_id}/reviews/summary` | ⑤ |  |
| 28 | 리뷰 | 리뷰 검색 (ES) | `GET /api/reviews/search?q=` | ⑤ |  |
| 29 | 사양 | 게임 최소·권장 사양 | `GET /api/games/{game_id}/requirements` | ⑥ |  |
| 30 | 사양 | 내 PC 사양 등록·조회 | `PUT·GET /api/me/specs` | ⑥ | ✓ |
| 31 | 사양 | 사양 적합도 판정 (AI) | `GET /api/games/{game_id}/spec-check` | ⑥ | ✓ |
| 32 | 동접자 | 동접자 기반 인기 게임 | `GET /api/games/players/top` | ⑦ |  |
| 33 | 동접자 | 접속자 적은 온라인 게임 경고 | `GET /api/games/players/low` | ⑦ |  |
| 34 | 검색 | 실시간 검색어 | `GET /api/search/trending` | ⑨ |  |
| 35 | 검색 | 최근 검색어 | `GET /api/search/recent` | ⑨ | ✓ |
| 36 | 운영 | 클릭스트림 수집 → Kafka | `POST /api/events` | 공통 |  |
| 37 | 운영 | API 사용 순위 | `GET /api/stats/api-ranking` | ⑩ |  |
| 38 | 운영 | 헬스체크 (HAProxy) | `GET /api/health` | 공통 |  |

분류별: 인증 4 · 게임 5 · 가격 5 · 구매 타이밍 2 · 찜·알림 6 · 추천 3 · 리뷰 3 · 사양 3 · 동접자 2 · 검색 2 · 운영 3 = **38**

## 응답 예시
`GET /api/games/119133/prices`
```json
{ "game_id": 119133,
  "items": [ { "store": "steam", "edition": "digital", "price_krw": 47900, "regular_krw": 64800,
               "discount_pct": 26, "url": "https://...", "collected_at": "2026-11-19T02:30:00Z" } ],
  "lowest": { "store": "steam", "price_krw": 47900 } }
```
`GET /api/games/119133/prediction`
```json
{ "game_id": 119133, "avg_sale_interval_days": 62, "next_sale_expected": "2026-12-21",
  "expected_discount_pct": 40, "confidence": "medium", "basis": "최근 2년 할인 9회 기준" }
```
`GET /api/games/119133/reviews/summary`
```json
{ "game_id": 119133, "positive_ratio": 0.92, "summary": "AI 요약 한두 줄",
  "pros": ["보스전", "탐험", "아트"], "cons": ["최적화", "난이도"], "generated_by": "ai", "updated_at": "2026-11-19T18:00:00Z" }
```
`GET /api/games/119133/spec-check`
```json
{ "game_id": 119133, "verdict": "min_ok", "reason": "GPU가 권장보다 낮아 옵션을 낮춰야 해요", "generated_by": "ai", "cached": true }
```
`GET /api/search/trending`
```json
{ "window": "1h", "items": [ { "rank": 1, "query": "엘든 링", "count": 132, "change": "up" } ] }
```
