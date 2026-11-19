# frontend — 웹 화면

**하는 일:** 사용자 화면. 데이터는 항상 `/api`(짝 Backend)로 받는다.
**배포:** Frontend 1·2 VM — nginx가 빌드 결과를 서빙하고 `/api`를 짝 Backend로 전달 (`nginx/`).

## 지킬 것
- 프레임워크: **팀 확정 필요** (권장 React + Vite). 확정되면 이 줄을 고치고 `docs/decisions.md`에 기록.
- API 주소는 상대경로 `/api/...`만 쓴다. Backend 호스트를 코드에 쓰지 않는다 (nginx가 연결).
- 응답 형식은 `docs/contracts/api.md` 기준. Backend가 준비되기 전에는 `mocks/`의 가짜 데이터로 개발.
- 화면 목록: 메인, 검색 결과, 게임 상세, 로그인·회원가입, 마이페이지, 알림 설정.
- 금액은 `price_krw`를 `toLocaleString('ko-KR')`로 표시, 시간은 KST로 변환해 표시.
- 클릭스트림: 검색·상세 보기·스토어 클릭·알림 등록 때 `POST /api/events`.
