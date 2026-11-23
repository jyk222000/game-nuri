# frontend — 웹 화면

**하는 일:** 사용자 화면. 데이터는 항상 `/api`(짝 Backend)로 받는다.
**배포:** Frontend 1·2 VM — nginx가 빌드 결과를 서빙하고 `/api`를 짝 Backend로 전달 (`nginx/`).

## 지킬 것
- 프레임워크: **팀 확정 필요** (권장 React + Vite). 확정되면 이 줄을 고치고 `docs/decisions.md`에 기록.
- API 주소는 상대경로 `/api/...`만 쓴다. Backend 호스트를 코드에 쓰지 않는다 (nginx가 연결).
- 응답 형식은 `docs/contracts/api.md` 기준. 목(`src/api/mock/`)도 같은 형식으로 응답한다 (플랫폼은 ERD 코드, 가격 키는 `platform`·`item_condition`, 이력은 `collected_at`).
- **API 모드** `VITE_API_MODE` (`src/api/client.js`):
  - `mock`(기본): 전부 목. Backend 없이 개발.
  - `hybrid`: Backend에 구현된 공개 조회 API(`REAL_READY` 목록)만 실서버로 부르고, 실패(404·5xx·연결 불가)하면 목으로 대신한다. 수집 가동 후 DB가 채워지는 동안 사용.
  - `real`: 전부 실서버. 구글 로그인도 실제로 동작. 모든 API가 구현·적재된 뒤에 사용.
  - Backend에 API가 새로 구현되면 `REAL_READY`에 정규식을 추가한다.
- 표시 이름 변환은 프런트가 한다: 플랫폼 코드 → `platformName()`, 스토어 → `storeName()`, 표지 색(`hue`)은 `hueOf(game_id)`로 만들고 `cover_url`이 있으면 이미지를 쓴다.
- 화면 목록: 메인, 검색 결과, 게임 상세, 로그인·회원가입, 마이페이지, 알림 설정.
- 금액은 `price_krw`를 `toLocaleString('ko-KR')`로 표시, 시간은 KST로 변환해 표시.
- 클릭스트림: 검색·상세 보기·스토어 클릭·알림 등록 때 `POST /api/events`.
