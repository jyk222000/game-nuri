# frontend — 웹 화면

**하는 일:** 사용자 화면. 데이터는 항상 `/api`(짝 Backend)로 받는다.
**배포:** Frontend 1·2 VM — nginx가 빌드 결과를 서빙하고 `/api`를 짝 Backend로 전달 (`nginx/`).

## 지킬 것
- 프레임워크: **React 18 + Vite 5** (빌드 결과를 nginx가 서빙, 2026-11-28 `docs/decisions.md`에 기록).
- API 주소는 상대경로 `/api/...`만 쓴다. Backend 호스트를 코드에 쓰지 않는다 (nginx가 연결).
- 응답 형식은 `docs/contracts/api.md` 기준. 목(`src/api/mock/`)도 같은 형식으로 응답한다 (플랫폼은 ERD 코드, 가격 키는 `platform`·`item_condition`, 이력은 `collected_at`).
- **API 모드** `VITE_API_MODE` (`src/api/client.js`):
  - `real`(기본): 전부 실서버(`/api`). 구글 로그인도 실제로 동작. 아직 Backend에 없는 API는 오류로 보인다.
  - `mock`: 전부 목. Backend 없이 화면만 개발할 때 `VITE_API_MODE=mock`으로 명시한다.
- 표시 이름 변환은 프런트가 한다: 플랫폼 코드 → `platformName()`, 스토어 → `storeName()`, 표지 색(`hue`)은 `hueOf(game_id)`로 만들고 `cover_url`이 있으면 이미지를 쓴다.
- 화면 목록: 메인, 검색 결과, 게임 상세, 로그인·회원가입, 마이페이지, 알림 설정.
- 금액은 `price_krw`를 `toLocaleString('ko-KR')`로 표시, 시간은 KST로 변환해 표시.
- 클릭스트림: 검색·상세 보기·스토어 클릭·알림 등록 때 `POST /api/events`.
