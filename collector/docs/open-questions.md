# 수집기 미결정 사항 (팀 합의 필요)

> 작성 2026-11-23 · 한예찬. 정해지면 `docs/decisions.md`에 한 줄 남기고 이 표에서 지운다.

| # | 내용 | 왜 막혔나 | 영향 | 필요한 것 |
|---|---|---|---|---|
| 1 | **ITAD 가격 이력(`games/history/v2`, USD)을 수집할지** | 정제기에 이력을 받는 kind가 없고 `shared/messages.py`의 `Kind`에도 없다 | ② 구매 타이밍·이력 그래프, 분석 A1 | 이력을 ITAD로 채울지 우리가 쌓는 스냅샷으로 채울지 결정. ITAD로 하면 `shared/`·`docs/contracts/` 별도 PR(+이고은 정제기, 남현식 Sink) |
| 2 | **환율 출처** (현재 환율 vs 날짜별 환율) | `history/v2`가 USD뿐이라 정제에서 환산해야 한다 | #1을 하면 이력의 원화 정확도 | 정제 담당(이고은) 결정 |
| 3 | ~~Kafka 전송 성공 여부 확인~~ **해결 (2026-11-23)** | 전달 콜백으로 성공·실패를 세고, 실패가 있으면 오류 로그와 종료 코드 1. 상세는 `igdb.md` | – | 실제 Kafka 서버에서의 시험만 남음 |
| 5 | **Steam 리뷰 한 건 단위 전송 → 계약·Connect 후속** | **수집기는 2026-11-23에 리뷰 1건 = 메시지 1개로 바꿨다.** 남은 것: ① `docs/contracts/messages/raw.steam.json`의 review 예시가 아직 페이지 단위(`reviews[]`) ② `pipeline/connect/mongo-sink-reviews.json`이 `raw.steam` 전체를 받는다(앱 정보·동접자 메시지도 `reviews`에 들어감) | ⑤ 리뷰 요약 전체 | ① 계약 예시 수정(별도 PR, 전원 리뷰). ② 남현식: `kind=review`만 거르고, 문서 `_id`를 `payload.recommendationid`로 하면 같은 리뷰가 다시 와도 중복되지 않는다(upsert). ES 필드 경로는 `payload.review`(본문), `payload.voted_up`, `payload.steam_appid` |
| 10 | **화면용 리뷰 수·긍정 비율 수집** | 페이지 단위 `query_summary`를 더 이상 보내지 않는다. 계획했던 `GetItems`(`reviews.summary_language_specific`)는 아직 수집기에 없다 | ⑤ 화면의 `review_count_ko`·`positive_pct`, `refined.review_summary` | 수집기에 `GetItems` 호출(한 번에 여러 게임, 키 불필요)을 추가할지 결정 (`steam-notes.md` 3절). 추가하면 새 `kind`가 필요한지 확인 (`shared/` 변경 여부) |
| 6 | **Steam 리뷰 게임당 수집량** | 지금 최초 500건 상한은 임시값 | ⑤ 키워드 품질, 수집 시간 | ⑤ 담당과 정한다. 정해지면 `--max-reviews` 기본값만 바꾸면 된다 |
| 7 | **보유 게임(`owned_games`) 요청 방식** | 사용자 요청 때 도는 흐름이라 주기 수집기가 아니다 | ④ 플레이 성향 | Backend(김준영)와 방식 결정 |
| 8 | **다나와 상품의 게임 매칭·본체 번들 제외** | 수집기는 게임 카테고리 상품을 그대로 보내므로 본체 번들·DLC가 섞인다 | ① 콘솔 가격 비교의 정확도 | 정제기(이고은)가 별칭 표로 매칭할 때 본체 번들·에디션 토큰을 거른다 (`danawa-notes.md` 5·6·11절 규칙). **별칭 보강(AI·자모 변환)은 지금 정하지 않는다.** 파이프라인을 한 번 끝까지 돌려 `refined.unmatched`를 본 뒤, 매칭에 실패한 판매자 표기만 보강한다. 검색어에는 별칭을 쓰지 않는다(IGDB 한국어 별칭이 한글 이름 없는 게임 339건 중 3건뿐, `danawa.md` 참고) |
| 9 | **다나와 빈 플랫폼 보강 검색 · 개별 판매처 상품** | 요청이 약 3배(≈7시간)로 늘어 6시간 주기를 넘긴다 | 콘솔 중고·일부 플랫폼 가격 누락 | 주기를 늘리거나 게임 수를 줄이거나 보강만 하루 1회로 분리할지 결정 |
| 4 | 수집 스케줄 | systemd 타이머가 없다 | 모든 수집기 (IGDB 매일, ITAD 6시간) | `proxy` VM에 배포할 때 함께 (서버 명령은 사전 확인) |
