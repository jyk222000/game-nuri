# Backend API 명세 (초안)

- 기본 경로 `/api`, JSON, 키는 `snake_case`, 시간은 UTC ISO 8601
- 인증: 로그인 후 세션 쿠키 (세션은 Valkey 저장)
- 오류 형식: `{"error": {"code": "NOT_FOUND", "message": "게임을 찾을 수 없습니다"}}`
- 목록 응답: `{"items": [...], "total": 123, "page": 1, "size": 20}`

| 메서드 | 경로 | 설명 | 인증 |
|---|---|---|---|
| GET | `/api/health` | 상태 확인 (HAProxy health check) | – |
| GET | `/api/games?q=&platform=&page=` | 게임 검색 (ES) | – |
| GET | `/api/games/deals?sort=discount` | 할인 중인 게임 (메인) | – |
| GET | `/api/games/{game_id}` | 게임 상세 | – |
| GET | `/api/games/{game_id}/prices` | 스토어별 현재가 | – |
| GET | `/api/games/{game_id}/history?days=180` | 가격 이력 | – |
| GET | `/api/games/{game_id}/timing` | 구매 타이밍 판단 | – |
| POST | `/api/auth/signup` | 회원가입 | – |
| POST | `/api/auth/login` | 로그인 | – |
| POST | `/api/auth/logout` | 로그아웃 | ✓ |
| GET | `/api/me` | 내 정보 | ✓ |
| PUT | `/api/me/steam` | Steam ID 연동 | ✓ |
| GET | `/api/me/steam/games` | 보유 게임·플레이타임 | ✓ |
| GET | `/api/me/alerts` | 내 알림 목록 | ✓ |
| POST | `/api/me/alerts` | 목표가 알림 등록 | ✓ |
| DELETE | `/api/me/alerts/{alert_id}` | 알림 해제 | ✓ |
| POST | `/api/events` | 클릭스트림 수집 → Kafka | – |

## 응답 예시
`GET /api/games/119133/prices`
```json
{
  "game_id": 119133,
  "items": [
    { "store": "steam", "edition": "digital", "price_krw": 47900, "regular_krw": 64800,
      "discount_pct": 26, "url": "https://...", "collected_at": "2026-11-19T02:30:00Z" }
  ],
  "lowest": { "store": "steam", "price_krw": 47900 }
}
```

`GET /api/games/119133/timing`
```json
{ "game_id": 119133, "verdict": "buy_now | wait | neutral",
  "reason": "역대 최저가와 3% 차이", "all_time_low_krw": 46500, "next_sale_expected": "2026-12-20" }
```
