# 수집기 미결정 사항 (팀 합의 필요)

> 작성 2026-11-23 · 한예찬. 정해지면 `docs/decisions.md`에 한 줄 남기고 이 표에서 지운다.
> 2026-11-23 `origin/main`(PR #48)과 정제기 브랜치(`NW2-32`, `NW2-34`)를 확인해 해결된 항목을 갱신했다.

## 열려 있는 것
| # | 내용 | 왜 막혔나 | 영향 | 필요한 것 |
|---|---|---|---|---|
| 4 | 수집 스케줄 | systemd 타이머가 없다 | 모든 수집기 (IGDB 매일, ITAD 현재가 6시간, **ITAD 이력 처음 1번 + 주 1번(`--since-days 14`)**, Steam 사양 매일·동접자 1시간·리뷰 매일, 다나와 6시간) | `proxy` VM에 배포할 때 함께 (서버 명령은 사전 확인). 다나와는 2.3시간짜리라 실행이 겹치지 않게 막아야 한다 |
| 5 | **Steam 리뷰 한 건 단위 전송 → 계약·Connect 후속** | 수집기는 리뷰 1건 = 메시지 1개로 바꿨다. 남은 것: ① `docs/contracts/messages/raw.steam.json`의 review 예시가 페이지 단위(`reviews[]`) → **별도 PR B로 수정 준비됨** ② `pipeline/connect/mongo-sink-reviews.json`이 `raw.steam` 전체를 받는다(앱 정보·동접자 메시지도 `reviews`에 들어감) ③ `infra/mongodb`의 `reviews` 고유 인덱스가 최상위 `recommendationid` 기준이라 `null` 중복으로 쓰기가 막힐 수 있다 | ⑤ 리뷰 요약 전체 | ② 남현식: `kind=review`만 거르고 문서 `_id`를 `payload.recommendationid`로 (upsert). ③ 김준영: 고유 인덱스를 `payload.recommendationid`로. ES 필드 경로는 `payload.review`, `payload.voted_up`, `payload.steam_appid` |
| 6 | **Steam 리뷰 게임당 수집량** | 지금 최초 500건 상한은 임시값 | ⑤ 키워드 품질, 수집 시간 | ⑤ 담당과 정한다. 정해지면 `--max-reviews` 기본값만 바꾸면 된다 |
| 7 | **보유 게임(`owned_games`) 요청 방식** | 사용자 요청 때 도는 흐름이라 주기 수집기가 아니다 | ④ 플레이 성향 | Backend(김준영)와 방식 결정 |
| 8 | **다나와 별칭 보강 시점** | 상품→게임 연결과 본체 번들·DLC·에디션·해외판 거르기는 정제기 브랜치 `NW2-34`에 구현되어 있다(미합침). 별칭 보강(AI·자모 변환)은 정하지 않았다 | ① 콘솔 가격 비교의 정확도 | 파이프라인을 한 번 끝까지 돌려 `refined.unmatched`를 본 뒤, 매칭에 실패한 판매자 표기만 보강한다. 검색어에는 별칭을 쓰지 않는다(IGDB 한국어 별칭이 한글 이름 없는 게임 339건 중 3건뿐, `danawa.md` 참고) |
| 9 | **다나와 빈 플랫폼 보강 검색 · 개별 판매처 상품** | 요청이 약 3배(≈7시간)로 늘어 6시간 주기를 넘긴다 | 콘솔 중고·일부 플랫폼 가격 누락 | 주기를 늘리거나 게임 수를 줄이거나 보강만 하루 1회로 분리할지 결정 |
| 10 | **화면용 리뷰 수·긍정 비율 수집** | 페이지 단위 `query_summary`를 더 이상 보내지 않는다. `GetItems`(`reviews.summary_language_specific`)는 아직 수집기에 없다 | ⑤ 화면의 `review_count_ko`·`positive_pct`, `refined.review_summary` | PR B(`review_summary` kind)가 합쳐진 뒤 수집기에 `GetItems` 호출을 추가한다(후속 PR). 값을 `refined.review_summary`에 넣는 방법은 이고은 결정 필요(upsert가 AI 요약 칼럼을 null로 덮어쓸 수 있음) |

## 해결됨
| # | 내용 | 결과 |
|---|---|---|
| 1 | ITAD 가격 이력(`games/history/v2`) 수집 | **수집한다** (PR #48, `raw.price`의 kind `price_history`, 처음 1번 + 주 1번). 수집기 구현은 이 브랜치 |
| 2 | 환율 출처 | **그 달 월평균 환율**로 정제에서 환산 (`NW2-32` 브랜치 구현·미합침, PR #48 계약). KRW는 그대로 쓴다 |
| 3 | Kafka 전송 성공 여부 확인 | 전달 콜백으로 성공·실패를 세고 실패 시 오류 로그와 종료 코드 1 (`igdb.md`). 실제 Kafka 서버 시험만 남음 |
