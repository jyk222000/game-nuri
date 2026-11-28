# Backend API 명세 (기능 명세서)

- **기능 단위 38개 = 엔드포인트(메서드+경로) 47개** (요구사항: 30개 이상). 아래 번호(#1~#38)는 기능 단위이고, API 명세서(엑셀)는 메서드+경로 단위로 47행이다. 기능 명세는 `docs/features.md`.
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
| 5 | 게임 | 검색 (한글·영문 부분 일치, 띄어쓰기·기호 무시, 오타·형태소는 ES: `SEARCH_BACKEND=es`일 때, ES 실패 시 MariaDB로 대체) | `GET /api/games?q=&platform=&genre=` | 공통 |  |
| 6 | 게임 | 자동완성 (띄어쓰기·기호 무시, ES는 쓰지 않음) | `GET /api/games/autocomplete?q=` | 공통 |  |
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
| 22 | 찜·알림 | 메일 수신 설정 | `GET·PUT /api/me/notifications` | ③ | ✓ |
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

분류별: 인증 4 · 게임 5 · 가격 5 · 구매 타이밍 2 · 찜·알림 6 · 추천 3 · 리뷰 3 · 사양 3 · 동접자 2 · 검색 2 · 운영 3 = **38(기능 단위)**

엔드포인트 수: 38 + 한 줄에 묶인 메서드·경로 9개(#1 +1, #2 +1, #3 +1, #8 +1, #17 +1, #19 +2, #22 +1, #30 +1) = **47**. 이 중 #28 리뷰 검색은 명세가 확정되지 않았고 구현 전이라, 구현된 엔드포인트는 46개다.

## 공통 규칙 (응답 형식은 프론트 목업 `frontend/src/api/mock/router.js`·`data.js` 기준, 2026-11-23 결정 반영)
- 시각: UTC ISO 8601 `Z` (`2026-11-19T02:30:00Z`). 날짜만 쓰는 필드는 `YYYY-MM-DD`(UTC).
- 목록: `{"items": [...], "total": 123, "page": 1, "size": 20}`. 페이지가 없는 목록(`genres`, `popular` 등)은 `{"items": [...]}`.
- **현재가**: `prices_current`에서 `item_condition='new'`인 행 중 `price_krw`가 가장 낮은 값(**PC 가격이 있는 게임은 PC 행 안에서만**, PC 가격이 없는 콘솔 전용 게임은 전체 플랫폼에서). 같으면 `store`·`platform` 이름순. 목록·카드·알림의 `price_krw`, `current_krw`가 이 값이다. 콘솔 가격은 `/prices`·`/lowest`의 플랫폼별 값으로 본다.
- `time_to_beat_hours`는 값이 없으면 `null`.
- `critic_score`는 IGDB 평론가 집계 점수(`aggregated_rating`, 0~100)를 정수로 반올림한 값이고 없으면 `null`이다. **메타크리틱 점수가 아니다**(화면에는 "평론가 점수(IGDB 집계)"로 표기한다).
- 할인 목록(`GET /api/games/deals`): **할인 중 = 새 상품 최저가의 `discount_pct` > 0**, 할인율 큰 순, `size` 기본 20 / 최대 100. 로그인 없이 보는 목록이라 `wished`는 항상 `false`.
- 역대 최저가(`GET /api/games/{id}/lowest`) 동점: 가장 이른 날짜 → `store`·`edition` 이름순.
- 가격 이력(`GET /api/games/{id}/history`)의 항목에는 `platform`·`item_condition`이 들어 있어, 필터 없이 불러도 플랫폼·상태를 구분할 수 있다.
- 예외: 찜 목록(`GET /api/me/wishlist`)·목표가 목록(`GET /api/me/alerts`)은 `page`·`size` 없이 `{"items": [...], "total": N}`만 준다.
- 오류: `{"error": {"code": "...", "message": "한국어 문장"}}`
  - **형식 검증 실패**(필드 누락·타입 오류 등)는 **422 + `INVALID_REQUEST`**, **업무 규칙 오류**(`INVALID_PRICE` 등)는 **400**.
  - **프런트는 HTTP status가 아니라 `error.code`로 처리한다.** `message`는 한국어 문장이다.

| code | HTTP | 언제 |
|---|---|---|
| `UNAUTHORIZED` | 401 | 로그인 필요 (✓ API에 세션이 없거나 만료) |
| `NOT_FOUND` | 404 | 게임·알림이 없음 |
| `INVALID_REQUEST` | 422 | 요청 형식 오류 (필드 누락·타입 오류) |
| `INVALID_PRICE` | 400 | 목표가가 0 이하 |
| `INVALID_STEAM_ID` | 400 | Steam ID가 17자리 숫자가 아님 |
| `SPEC_REQUIRED` | 400 | PC 사양 미입력 상태에서 spec-check |
| `STEAM_PROFILE_PRIVATE` | 400 | Steam 프로필·게임 세부 정보가 비공개라 보유 게임을 못 가져옴 |
| `STEAM_REQUIRED` | 400 | Steam ID 미연동 상태에서 recommendations·taste |
| `UNAVAILABLE` | 503 | Valkey(세션) 등 의존 서비스 장애 |
| `INTERNAL` | 500 | 서버 오류 |

### 서버 정의 (구현 기준, 2026-11-23)
- `GET /api/games/{id}`의 `insights`는 **항상 `[]`** 이다(analysis 태그 형식 확정 전). `online_only` = `games.is_online`.
- **인기(`popular`)**: 찜한 사용자 수가 많은 순, 같으면 최근 동접자 많은 순. 찜도 동접자도 있는 게임이 하나도 없어 결과가 비면 **최근 할인 중인 게임**(할인율 큰 순)으로 채운다.
- **짧게 끝낼 게임(`short`)**: 보통 플레이 시간(`normally_sec`)이 10시간 이하인 게임, 짧은 순.
- **접속자 적은 온라인 게임(`players/low`)**: `is_online`이고 최근 동접자가 1000 미만인 게임, 적은 순.
- 공개 목록(`popular`·`short`·`players/*`·검색)은 로그인 없이 보는 목록이라 카드의 `wished`는 항상 `false`.

## 응답 예시
### 가격 키: `platform`, `item_condition` 추가 (목업 대비 변경)
가격 테이블 키가 `(game_id, store, edition, platform, item_condition)`이므로 가격 비교·이력·최저가 응답에 `platform`(`PC`, `PS5`, `PS4`, `Switch`, `Switch2`, `XboxSeries`, `XboxOne`)과 `item_condition`(`new` | `used`)을 넣는다. 목업의 `edition: "used"`는 `edition: "physical"` + `item_condition: "used"`로 바꾼다.

### 에디션 가격: `variant_name` 추가 (#93)
가격 행을 그대로 내려 주는 응답(`prices`의 `items`·`lowest`, `history`의 `items`, `lowest`의 `items`)에 `variant_name`을 넣는다.
- **본편 가격이면 `null`**, 본편이 아닌 에디션 가격이면 이름(예: `"얼티밋 에디션"`). `prices_current`·`price_history`의 `variant_name VARCHAR(64) NULL`을 그대로 내린다(erd.sql 11번).
- 다나와에서 그 게임·플랫폼·상태에 **본편 상품이 없을 때만** 에디션 가격을 싣는다(정제기 규칙). 같은 키에 본편과 에디션이 함께 들어오지 않으므로 **`variant_name`은 가격 키·중복 판단 키에 넣지 않는다.** ITAD(PC)는 항상 `null`.
- 화면은 값이 있을 때 "얼티밋 에디션"처럼 표시해 본편 가격이 아님을 알린다.
- **이번 범위 밖**: 카드·상세의 `price_krw`와 구매 타이밍(`/timing`)에는 넣지 않는다. 카드는 PC 우선이라 PC 가격이 없는 콘솔 전용 게임에서만 에디션 가격이 카드에 나올 수 있고, 그때의 표시(`price_platform`과 함께)는 따로 정한다.

`GET /api/games/119133/prices`
```json
{ "game_id": 119133,
  "items": [
    { "store": "steam", "edition": "digital", "platform": "PC", "item_condition": "new",
      "price_krw": 47900, "regular_krw": 64800, "discount_pct": 26, "url": "https://...", "variant_name": null, "price_original": 59.99, "currency_original": "USD", "collected_at": "2026-11-19T02:30:00Z" },
    { "store": "danawa", "edition": "physical", "platform": "PS5", "item_condition": "used",
      "price_krw": 38000, "regular_krw": null, "discount_pct": null, "url": "https://...", "variant_name": "얼티밋 에디션", "price_original": null, "currency_original": null, "collected_at": "2026-11-19T02:30:00Z" } ],
  "lowest": { "store": "steam", "edition": "digital", "platform": "PC", "item_condition": "new", "price_krw": 47900, "variant_name": null } }
```
- `prices`의 `items`에는 `price_original`(스토어가 준 원래 통화 가격, 환산 전)과 `currency_original`(예: `USD`)이 있고 없으면 `null`이다. 금액의 기준은 계속 원화 정수 `price_krw`이고, 원래 통화 값은 참고용 표시(예: "$59.99")에만 쓴다. `history`·`lowest`에는 넣지 않는다.
`GET /api/games/119133/history?days=180&platform=PC&item_condition=new`
```json
{ "game_id": 119133, "days": 180, "platform": "PC", "item_condition": "new",
  "items": [ { "store": "steam", "edition": "digital", "platform": "PC", "item_condition": "new",
               "collected_at": "2026-11-19T02:30:00Z", "price_krw": 47900, "regular_krw": 64800, "discount_pct": 26, "variant_name": null } ] }
```
**가격 이력 중복 제거 (결정)**
- 중복 판단 키: **`(game_id, store, edition, platform, item_condition, collected_at)`**. 같은 시각에 `edition`만 다른 행(digital·physical)은 서로 다른 행이다.
- **`price_history`에는 UNIQUE 키를 넣지 않는다.** insert 모드 JDBC Sink가 중복 행에서 멈추기 때문이다.
- 중복은 **refiner(적재 전)와 Backend 조회(응답 전)** 에서 막는다. 같은 키가 둘 이상이면 응답에는 한 건만 낸다(가장 나중에 들어온 행).

`GET /api/games/119133/lowest` — **platform·item_condition별** 역대 최저가 (콘솔은 "수집 이후 최저가")
```json
{ "game_id": 119133,
  "items": [ { "platform": "PC", "item_condition": "new", "store": "steam", "edition": "digital",
               "price_krw": 38900, "regular_krw": 64800, "discount_pct": 40, "variant_name": null, "date": "2025-12-05" },
             { "platform": "PS5", "item_condition": "used", "store": "danawa", "edition": "physical",
               "price_krw": 31000, "regular_krw": null, "discount_pct": null, "variant_name": "얼티밋 에디션", "date": "2026-10-02" } ] }
```

### 인증·내 정보
`GET /api/auth/google/login`, `/callback` → 구글로 리다이렉트, 콜백 후 세션 쿠키 발급 후 `/`로 이동 (본문 없음).
`POST /api/auth/refresh`, `POST /api/auth/logout` → `{ "ok": true }`
`GET /api/me` / `PATCH /api/me` — `name`은 `users.nickname`, **`picture`는 응답에서 뺀다**
```json
{ "user_id": 1, "email": "gamer@example.com", "name": "겜누리 사용자", "steam_id": "76561198000000000" }
```
`PUT /api/me/steam` 본문 `{ "steam_id": "76561198000000000" }` → `{ "steam_id": "76561198000000000", "owned_games": 126 }`
- **Backend가 Steam `GetOwnedGames`를 직접 호출**해 `user_owned_games`에 `appid`·플레이 시간(분)만 저장한다(collector·pipeline은 관여하지 않음). 같은 ID로 다시 부르면 보유 게임을 새로 고친다(그 사용자의 기존 행을 교체). Steam 조회가 실패하면 Steam ID도 저장하지 않는다.
- 프로필·게임 세부 정보가 **비공개**(Steam이 빈 응답)이면 400 `STEAM_PROFILE_PRIVATE`(메시지로 공개 설정을 안내). Steam 장애·키 미설정은 503 `UNAVAILABLE`.

### 게임
카드 (`GET /api/games`, `popular`, `deals`, `short`, `players/top`, `players/low`, 찜 목록, 추천에 공통). `platforms`는 ERD 코드이고 **표시 이름은 프런트가 바꾼다.**
```json
{ "game_id": 119133, "name": "엘든 링", "name_en": "Elden Ring", "genres": ["액션", "RPG"], "platforms": ["PC", "PS5", "XboxSeries"],
  "cover_url": "https://...", "price_krw": 47900, "regular_krw": 64800, "discount_pct": 26,
  "positive_ratio": 0.92, "concurrent_players": 412000, "time_to_beat_hours": 60, "critic_score": 87, "wished": false }
```
(목업의 `hue`는 ERD에 없어 `cover_url`로 대체한다, 아래 표 4번)
`GET /api/games?q=&platform=&genre=&sort=price|discount|popular|rating&length=short|medium|long&page=&size=` → `{ "items": [카드], "total": 1, "page": 1, "size": 20 }` (`platform` 값은 ERD 코드. `popular`는 `/api/games/popular`와 같은 기준(찜한 사용자 수 → 최근 동접자 → game_id 순)으로 정렬하고, 찜·동접자가 없는 게임은 제외하지 않고 뒤에 이름순으로 둔다. 다른 조건과 함께 쓸 수 있다. `rating`은 `critic_score` 높은 순, 같으면 평론 수(`critic_count`) 많은 순이고 점수가 없는 게임은 제외하지 않고 맨 뒤에 이름순이다. `length`는 "보통" 클리어 시간(`game_time_to_beat.normally_sec`) 구간 조건으로 `short` 10시간 이하, `medium` 10시간 초과~40시간 이하, `long` 40시간 초과이며 클리어 시간 정보가 없는(없거나 0) 게임은 제외한다(40시간은 임시 기준). `sort`·`length`는 `q`·`platform`·`genre`와 함께 쓸 수 있고 값이 틀리면 422 `INVALID_REQUEST`)
`GET /api/games/autocomplete?q=` → `{ "items": [ { "game_id": 119133, "name": "엘든 링", "name_en": "Elden Ring" } ] }`
`GET /api/games/popular`, `deals`, `short`, `players/top` → `{ "items": [카드] }`. `players/low` 카드에는 `"warning": "접속자가 적어 매칭이 어려울 수 있어요"` 추가
`GET /api/genres`, `/api/tags` → `{ "items": ["액션", "RPG"] }`
`GET /api/exchange-rates` → **USD·EUR·GBP만** (JPY는 프런트에서 뺀다)
```json
{ "base": "KRW", "rates": { "USD": 1385.2, "EUR": 1502.8, "GBP": 1760.4 }, "updated_at": "2026-11-21T00:00:00Z" }
```
`GET /api/games/119133` → 카드 필드 + 아래
```json
{ "release_date": "2022-02-25", "summary": "...", "tags": ["오픈월드", "소울라이크"], "online_only": false,
  "steam_app_id": 1245620, "lowest_krw": 38900,
  "time_to_beat": { "hastily_hours": 8.5, "normally_hours": 12.0, "completely_hours": 25.5, "count": 842 },
  "critic_count": 24, "user_score": 78, "user_score_count": 120,
  "korean_supported": true, "age_rating": 0,
  "developers": ["FromSoftware"], "publishers": ["Bandai Namco"],
  "series": [ { "kind": "franchise", "name": "Souls", "games": [ { "game_id": 1, "name": "...", "cover_url": "https://..." } ] } ],
  "parent_game": null, "version_parent": null, "dlcs": [ { "game_id": 2, "name": "...", "cover_url": null } ], "editions": [],
  "review_stats": { "label_ko": "매우 긍정적", "count_ko": 120, "positive_pct_ko": 91, "score_ko": 8, "label_all": "대체로 긍정적", "count_all": 5000, "positive_pct_all": 88 },
  "insights": [ { "...": "analysis/가 만든 게임별 태그 (모양은 analysis 담당과 확정)" } ] }
```
- `time_to_beat`는 IGDB 클리어 시간 3종(빠르게·보통·완벽하게, 시간 단위 소수 첫째 자리)과 집계 인원이다. `game_time_to_beat` 행이 없으면 `null`이고, 값이 0이거나 없으면 그 값만 `null`이다. 카드의 `time_to_beat_hours`(보통, 정수)는 그대로다.
- `critic_score`(카드 필드)와 `critic_count`(IGDB 평론 집계 수)는 점수가 없으면 둘 다 `null`이다. `critic_count`는 상세에만 있다.
- `user_score`·`user_score_count`: IGDB 사용자 평점(0~100, 정수 반올림)과 평가 수. 평점이 없으면 둘 다 `null`.
- `korean_supported`: Steam 지원 언어에 한국어가 있는지(`games.korean_supported`). `age_rating`: Steam `required_age`(정수, 0=제한 없음, `games.age_rating`). 값을 모르면 `null`.
- `developers`·`publishers`: 개발사·배급사 이름(이름순, 없으면 `[]`). `game_companies`·`companies`.
- `series`: 이 게임이 속한 시리즈(`kind`: `collection`|`franchise`). 각 시리즈의 `games`는 같은 시리즈의 **다른** 게임(최대 12개, 출시일순·출시일 없는 게임은 뒤, `name`은 한글명 우선). 없으면 `[]`.
- `parent_game`(DLC·확장이면 본편), `version_parent`(에디션이면 원본)는 `games`에 있는 게임만 채우고 아니면 `null`. `dlcs`(이 게임을 `parent_game_id`로 가리키는 게임)·`editions`(`version_parent_id`로 가리키는 게임)는 최대 20개, 없으면 `[]`.
- `review_stats`: Steam 스토어 리뷰 등급·수(`game_review_stats`). 한국어(`*_ko`, 스토어 표시값)와 전체 언어(`*_all`)를 따로 준다. `score_ko`는 Steam 등급 1~9. 행이 없으면 `null`. 카드의 `positive_ratio`와 별개다.

### 구매 타이밍
`GET /api/games/119133/timing`
```json
{ "game_id": 119133, "verdict": "buy_now", "reason": "역대 최저가에 가까운 가격이에요. 지금 사도 손해가 적어요.", "current_krw": 40500,
  "lowest_krw": 38900, "lowest_date": "2025-12-05", "vs_lowest_pct": 4, "sale_count_2y": 9 }
```
`verdict`: `buy_now` | `neutral` | `wait` | `insufficient_data` ← 마지막 값은 목업에 없는 값(확정)
- **기준 이력은 PC·새 상품(`item_condition='new'`)** 이다. 하루에 여러 건이면 그날 최저가 한 줄만 쓴다. 따라서 **`current_krw`는 이 이력의 최신 값**이며, 카드의 현재가(PC 우선 새 상품 최저가)와 **PC 가격이 있는 게임에서는 같다.** 콘솔 전용 게임은 `insufficient_data`라 비교할 값이 없다.
- **`insufficient_data` 조건**: PC·새 상품 이력이 없거나(콘솔 전용 포함), **이력 일수가 3 미만**(하루 한 줄로 합친 뒤 날짜 수)일 때. 이때 `current_krw`, `lowest_krw`, `lowest_date`, `vs_lowest_pct`, `sale_count_2y`는 `null`이고 `reason`에 이유를 쓴다. (정상 판정에서도 역대 최저가가 0원이었다가 지금은 유료이면 `vs_lowest_pct`만 `null`이다. 계속 무료이면 0.)
- 판정 규칙(임시, analysis A1 확정 전 — 프런트 목업도 같게 맞춘다), 위에서부터 먼저 맞는 것:
  1. 현재가가 0원이면 `buy_now`("무료예요").
  2. **현재가가 역대 최저가의 105% 이하(같은 값 포함)이고 '내려간 가격'이면 `buy_now`** — 할인율과 무관하다. '내려간 가격' = 현재 할인율 ≥ 10% **또는** 역대 최저가가 이력 최고가보다 10% 이상 낮음. (스토어가 할인율을 주지 않는 다나와 행은 `discount_pct`가 비어 있어서 이력으로 판단한다. 가격이 한 번도 변하지 않은 게임은 현재가=최저가=정가이므로 여기에 해당하지 않는다.)
  3. 현재 할인율 ≥ 10이면 `neutral` (2번에 걸리지 않았으므로 현재가는 최저가의 105%보다 높다).
  4. 그 외 `wait`.
- `reason` 문구는 프런트 목업(`router.js`)과 같다: `buy_now` 현재가=최저가면 "역대 최저가와 같은 가격이에요. 지금 사도 손해가 적어요.", 최저가보다 높지만 105% 이하면 "역대 최저가에 가까운 가격이에요. 지금 사도 손해가 적어요." / `neutral` "할인 중이지만 역대 최저가(N원)보다는 높아요. 급하지 않다면 더 기다려도 좋아요." / `wait` "정가에 가까워요." (다음 할인 예상일이 있으면 " 다음 할인은 YYYY-MM-DD 전후로 예상돼요." 추가). 예시 숫자(40,500 / 38,900)는 규칙(105% 이하)에 맞춘 값이다.

`GET /api/games/119133/prediction`
```json
{ "game_id": 119133, "avg_sale_interval_days": 62, "next_sale_expected": "2026-12-21",
  "expected_discount_pct": 40, "confidence": "medium", "basis": "최근 2년 할인 9회 기준" }
```
- **이력이 부족하거나 최근 2년 할인이 2회 미만이면** `confidence`는 `"insufficient_data"`이고 `avg_sale_interval_days`, `next_sale_expected`, `expected_discount_pct`는 `null`이다(`basis`에 이유). `confidence`: `high`(할인 8회 이상) | `medium`(4회 이상) | `low` | `insufficient_data`.
- **예상일이 이미 지났으면** 오늘 + 14일로 계산한다.

### 찜·알림 (모두 ✓)
`GET /api/me/wishlist` → `{ "items": [카드], "total": 1 }`
`POST /api/me/wishlist` 본문 `{ "game_id": 119133 }` → 200 `{ "game_id": 119133, "wished": true }` (이미 찜했어도 200, 멱등)
`DELETE /api/me/wishlist?game_id=119133` → `{ "game_id": 119133, "wished": false }` (찜하지 않았어도 같은 응답, 멱등)
`GET /api/me/alerts` → `{ "items": [ { "alert_id": 3, "game_id": 119133, "game_name": "엘든 링", "target_price_krw": 40000, "current_krw": 47900, "active": true, "created_at": "...Z" } ], "total": 1 }`
`POST /api/me/alerts` 본문 `{ "game_id": 119133, "target_price_krw": 40000 }` → 알림 한 건. **(user_id, game_id)가 이미 있으면 409가 아니라 덮어쓴다.** `target_price_krw`가 0 이하이면 400 `INVALID_PRICE`
`PATCH /api/me/alerts/{alert_id}` 본문 `{ "target_price_krw"?, "active"? }` → 알림 한 건 (없거나 남의 것이면 404 `NOT_FOUND`)
`DELETE /api/me/alerts/{alert_id}` → `{ "ok": true }` (없거나 남의 것이면 404 `NOT_FOUND`. 그 알림의 `alert_logs`는 FK `ON DELETE CASCADE`로 함께 지워진다)
`GET /api/me/alerts/logs` → `alert_logs`에 `alerts`·`games`를 조인해 `game_id`, `game_name`, `target_price_krw`를 채우고 **`channel`은 `"email"` 고정**
```json
{ "items": [ { "log_id": 9, "game_id": 119133, "game_name": "엘든 링", "price_krw": 38900, "target_price_krw": 40000,
               "store": "steam", "sent_at": "2026-11-19T02:30:00Z", "channel": "email" } ], "total": 1 }
```
`GET /api/me/notifications`, `PUT /api/me/notifications` 본문 `{ "email_enabled": true }` → **`email_enabled` 하나** (`notification_settings`와 같음). 행이 없으면 `true`로 응답
```json
{ "email_enabled": true }
```
(목업의 `price_alert`, `weekly_deals`는 프런트에서 뺀다. API 개수는 38개 그대로, #22 경로가 `GET·PUT`이 된다.)

### 추천 (✓)
`GET /api/me/taste` → `{ "total_playtime_hours": 1840, "owned_games": 126, "top_genres": [ { "genre": "액션", "pct": 38 } ], "style": "긴 호흡의 액션·RPG를 즐기는 탐험가형", "preferred_length": "long", "recent_games": [ { "game_id": 119133, "name": "엘든 링", "cover_url": "https://...", "last_played_at": "2026-11-20T09:30:00Z", "playtime_hours": 60 } ] }`. `preferred_length`는 `"short"|"medium"|"long"|null`이다. 플레이한(`playtime_forever_min` > 0) 보유 게임 중 클리어 시간이 있는 게임의 "보통" 클리어 시간 **중앙값**을 위 `length` 구간(10시간·40시간 기준)에 대입한 값이고, 그런 게임이 5개 미만이면 `null`이다(5개는 임시 기준). `recent_games`는 Steam 마지막 플레이 시각(`user_owned_games.rtime_last_played`)이 있는 보유 게임 중 최근 5개(최근 순, `playtime_hours`는 누적 시간)이고, 기록이 없으면 `[]`이다. `games`에 연결되지 않은 앱은 뺀다
`GET /api/me/recommendations` → `{ "items": [카드 + "reason": "RPG 장르를 많이 플레이했어요"] }` (`reason`은 `"<장르> 장르를 많이 플레이했어요"` 형식)

### 리뷰
리뷰 저장은 MongoDB `reviews` → Monstache → ES `reviews`(Steam 리뷰, 한국어)이고, 요약은 MariaDB `review_summaries`다.
목록(#26)·요약(#27)은 확정이고, **검색(#28)은 미확정**이다.

`GET /api/games/119133/reviews?page=1&size=10&sort=helpful` (로그인 불필요) → `{ "items": [ { "review_id": "240839937", "source": "steam", "recommended": true, "text": "...", "playtime_hours": 42, "created_at": "...Z" } ], "total": 412, "page": 1, "size": 10 }`
- `page` ≥ 1(기본 1), `size` 1~50(기본 10), `sort`: `helpful`(기본, 도움이 됐다는 반응(`votes_up`)이 많은 순, 같으면 최신순) | `recent`(최신순). 값이 틀리면 422 `INVALID_REQUEST`.
- 필드: `review_id`=Steam `recommendationid`(문자열), `recommended`=`voted_up`, `playtime_hours`=리뷰를 쓸 때까지의 플레이 시간(Steam의 분 단위를 시간으로 **반올림**, 값이 없으면 `null`), `created_at`=UTC ISO 8601(`...Z`).
- `text`는 리뷰 원문 전체다(길이 제한 없음). Steam BBCode(`[b]`, `[h1]`, `[list]` 등)가 섞인 원문이며 변환은 Frontend가 한다.
- 게임의 Steam 앱 ID(`game_store_ids`, store=`steam`)로 조회한다. **Steam 앱 ID가 없는 게임(콘솔 전용 등)은 `items: []`, `total: 0`** 이다. 없는 `game_id`는 404 `NOT_FOUND`.
- ES 기본 한도 때문에 시작 위치(`(page-1)*size`) + `size`가 10,000을 넘는 페이지는 422 `INVALID_REQUEST`. ES를 못 읽으면 503 `UNAVAILABLE`.

`GET /api/games/119133/reviews/summary` (로그인 불필요, `review_summaries` 기준) → `{ "game_id": 119133, "positive_ratio": 0.92, "summary": "...", "pros": ["보스전"], "cons": ["최적화"], "generated_by": "ai", "updated_at": "...Z" }`
- `pros`·`cons`는 `pros_keywords`·`cons_keywords`(쉼표 구분)를 목록으로 바꾼 것이다.
- `positive_ratio`는 카드의 긍정률과 **같은 값**이다(`game_review_stats`의 한국어 긍정률 → 전체 언어 → `review_summaries.positive_ratio` 순, 모두 없으면 `null`).
- **요약 행이 아직 없는 게임도 200**이다: `summary: null`, `pros: []`, `cons: []`, `generated_by: null`, `updated_at: null`(긍정률은 위 규칙대로 채워질 수 있다). 없는 `game_id`만 404 `NOT_FOUND`. `generated_by`는 `ai` | `fallback`(AI 실패 시 키워드만).
- Backend는 AI를 부르지 않고 `review_summaries`를 읽기만 한다.

`GET /api/reviews/search?q=` → 같은 형식 + `game_id`, `game_name` (**미확정**)

### 사양
`GET /api/games/119133/requirements` — **`game_requirements` 텍스트 컬럼 그대로** (`minimum_text`, `recommended_text`, `updated_at`). 구조화(`cpu`, `gpu` 등)는 ⑥ 사양 비교 방식이 정해지면 추가한다.
```json
{ "game_id": 119133, "minimum_text": "OS: Windows 10 ... 그래픽: GTX 1060 ...", "recommended_text": "OS: Windows 10/11 ...",
  "updated_at": "2026-11-19T02:30:00Z" }
```
`GET·PUT /api/me/specs` → `{ "cpu": "", "gpu": "", "ram_gb": null }` (`os` 추가 확정, 표 10번)
`GET /api/games/119133/spec-check` → `{ "game_id": 119133, "verdict": "min_ok", "reason": "...", "generated_by": "ai", "cached": true }` (`verdict`: `rec_ok` | `min_ok` | `below_min`)

### 검색·운영
`GET /api/search/trending` → `{ "window": "1h", "items": [ { "rank": 1, "query": "엘든 링", "count": 132, "change": "up" } ] }` (`change`: `up` | `down` | `same` | `new`)
`GET /api/search/recent` → `{ "items": ["엘든 링", "하데스"] }`
`POST /api/events` 본문 `{ "type": "search", "query": "...", "at": "...Z", ... }` → `{ "accepted": true }`. **요청은 `type`/`at`, Kafka 메시지는 `messages/clickstream.json`(`event`/`occurred_at`)으로 변환해 `clickstream` 토픽에 보낸다.** `at`(브라우저 시각)은 받기만 하고 `occurred_at`은 서버 시각(UTC)으로 기록한다. `session_id`(선택)는 브라우저가 만든 익명 UUID이며 로그인 세션 쿠키 값과 무관하다. Kafka가 안 되면 200 `{"accepted": false}`.
`GET /api/stats/api-ranking?size=10` → `{ "items": [ { "rank": 1, "api": "GET /api/games", "calls": 18240 } ], "status": "ok" }`. Backend가 Prometheus HTTP API(`PROMETHEUS_URL`)에서 `http_requests_total{handler,method}`의 최근 24시간 호출 수(`increase`)를 서버 1·2 합쳐 조회한다(`/api/health`·순위 API 자신은 제외). Prometheus 조회가 실패하면 200 `{ "items": [], "status": "degraded" }`.
`GET /api/health` → `{ "status": "ok", "server": "backend1", "db_write": "ok", "db_read": "ok", "valkey": "ok", "es": "ok" }`. Replica·Valkey·ES가 안 되면 200 `"status": "degraded"`, Primary가 안 되면 503 `"status": "down"`

## 목업과 ERD가 달랐던 곳 (2026-11-23 결정 상태)
| # | 목업 | ERD | 결정 | 상태 |
|---|---|---|---|---|
| 1 | 게임 `name`(한글) + `name_en`(영문) | `games.name`(영문) + `name_ko`(한글) | API `name` = `name_ko` 우선(없으면 `games.name`), `name_en` = `games.name` | 확정 |
| 2 | `me.name`, `me.picture` | `users.nickname`만 | `name` = `nickname`, `picture`는 응답에서 뺀다 | 결정 |
| 3 | `notifications` 3개 | `email_enabled` 하나 | `email_enabled` 하나. `price_alert`·`weekly_deals`는 프런트에서 뺀다 | 결정 |
| 4 | 카드 `hue` | 없음 (`cover_url`) | `cover_url`로 대체, `hue`는 프런트가 계산 | 확정 |
| 5 | `platforms`: `pc`/`ps`/`xbox`/`switch` | ERD 코드 7개 | ERD 코드를 쓰고 표시 이름은 프런트가 바꾼다 | 결정 |
| 6 | 가격 `edition: "used"` | `edition` + `item_condition` | `physical` + `used`로 표현 | 결정 |
| 7 | 이력 `date`, 단일 시리즈 | `collected_at`, 여러 시리즈 | `collected_at`, `store`·`edition` 포함, `platform`·`item_condition`으로 시리즈 선택 | 결정 |
| 8 | 최저가 단일 값 | 플랫폼·상태별 | `lowest`를 `items[]`로 | 결정 |
| 9 | `requirements` 구조화 | `minimum_text`, `recommended_text` | 텍스트 컬럼 그대로. 구조화는 ⑥ 방식 확정 후 | 결정 |
| 10 | `specs` 에 `os` 없음 | `user_specs.os` 있음 | `os`를 요청·응답에 추가 | 확정 |
| 11 | 알림 내역 `game_id`, `game_name`, `target_price_krw`, `channel` | `alert_logs`에 없음 | `alerts`·`games` 조인으로 채우고 `channel`은 `"email"` 고정 | 결정 |
| 12 | 알림 목록 `game_name`, `current_krw` | `alerts`에 없음 | 조인(`games`, `prices_current` 최저가)으로 채움 | 결정(구현 방식) |
| 13 | 카드 `positive_ratio` 등 | 조인·계산 | 스키마 변경 없음 | 결정(구현 방식) |
| 14 | 리뷰 필드 | MariaDB 테이블 없음 | 목록(#26)은 ES `reviews`, 요약(#27)은 `review_summaries`로 확정(위 '리뷰' 절). 검색(#28)만 "미확정" | 결정 |
| 15 | `exchange-rates`에 `JPY` | USD·EUR·GBP | USD·EUR·GBP만, JPY는 프런트에서 뺀다 | 결정 |
| 16 | `GET /api/me/notifications` | #22는 `PUT`만 | #22를 `GET·PUT`으로 적는다(38개 유지) | 결정 |
| 17 | 이력 중복 제거 | 고유 키 없음 | `(game_id, store, edition, platform, item_condition, collected_at)`, UNIQUE는 넣지 않고 refiner·조회에서 처리 | 결정 |
