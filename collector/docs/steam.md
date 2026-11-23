# Steam 수집기

> 작성 2026-11-23 · 담당 한예찬 · 코드: `collector/collector/sources/steam.py`, 시험: `collector/tests/test_steam.py`
> API 세부는 `docs/collector-test/steam-notes.md`. 세 가지 모두 **키가 필요 없다**.

## 하는 일
`games_1000.csv`의 `steam_appid`로 세 가지를 받아 **원본 그대로** `raw.steam`으로 보낸다. 모든 봉투의 `request.params.appid`에 appid를 넣는다(정제기의 게임 찾기 힌트). Kafka 키는 appid.

| kind | 호출 | 봉투 단위 | 주기 | 호출 간격 | 소요(1,000게임 추정) |
|---|---|---|---|---|---|
| `app_details` | `store.steampowered.com/api/appdetails` (`cc=kr`, `l=koreana`) | 게임 1건. payload = 응답 `{"<appid>": {success, data}}` 그대로 | 매일 | 1.6초 | 약 30분 |
| `player_count` | `ISteamUserStats/GetNumberOfCurrentPlayers/v1` | 게임 1건. payload = `{"response": {player_count, result}}` 그대로 | 1시간 | 0.3초 | 약 10분 |
| `review` | `IUserReviewsService/GetAppReviews/v1` (한국어, 최신순, `purchase_type=1`, 100건씩) | **리뷰 1건**. payload = 리뷰 객체 그대로 + `steam_appid`. Kafka 키는 `steam_appid` | 매일 | 0.5초 | 최초 약 1시간, 이후 수 분 |

## 리뷰 증분 수집
- 최신순으로 받다가 **이미 받은 리뷰를 만나면 그 페이지에서 멈춘다.** 이미 받은 리뷰는 보내지 않는다(중복 방지).
- **리뷰 1건 = 봉투 1개 (2026-11-23 변경).** Mongo `reviews`·ES에 리뷰가 한 건씩 문서가 되게 하려고 페이지 단위에서 바꿨다. 최초 실행은 게임당 최대 500건이라 메시지가 **최대 약 50만 개**(한 개 약 1KB)가 된다. 페이지 단위 필드(`query_summary`, `total_matching`, `cursor`)는 담지 않는다.
- payload 필드: `steam_appid`, `recommendationid`(문자열, 리뷰의 고유 번호), `review`(본문), `voted_up`, `votes_up`, `votes_funny`, `weighted_vote_score`, `timestamp_created`, `timestamp_updated`, `language`, `steam_purchase`, `received_for_free`, `refunded`, `written_during_early_access`, `author{playtime_forever, playtime_at_review, …}`, `hardware` 등 Steam 응답 그대로.
- 어디까지 받았는지는 `collector/state/steam_reviews.json`에 게임별로 저장한다 (가장 새 리뷰의 `timestamp_created`와 그 시각의 `recommendationid`들). Git에는 올라가지 않는다. **서버(`proxy`)에서 이 파일을 지우면 처음부터 다시 받는다.**
- 끝 조건: 0건 페이지 · 아는 리뷰를 만남 · 상한 도달 · cursor 없음/반복(안전장치).
- **게임당 새 리뷰 상한 `--max-reviews`(기본 500).** 최초 실행은 게임당 최신 500건만 받는다. ⑤ 요약에 몇 건이 필요한지 팀이 정하지 않아 정한 임시값이다.
- 한 게임이 실패하면 그 게임만 건너뛰고 계속한다(다음 실행에서 이어 받는다). 사양·동접자도 같다.
- **수정된 리뷰(갱신순 `filter=2`)와 삭제된 리뷰는 처리하지 않는다.** steam-notes 6절의 미해결 항목과 같다.

## 실행
`.env`가 없어도 된다(키 불필요). 루트에서 실행한다.
```bash
PYTHONPATH=collector python -m collector.main --source steam --kind app_details --dry-run --limit 3
PYTHONPATH=collector python -m collector.main --source steam --kind player_count
PYTHONPATH=collector python -m collector.main --source steam --kind review --max-reviews 500
```
`--dry-run` 샘플: `samples/raw.steam.<kind>.<appid>.json` (리뷰는 `raw.steam.review.<appid>.<recommendationid>.json`으로 한 건에 파일 하나라, `--limit`과 `--max-reviews`를 작게 줘야 한다).
**리뷰를 `--dry-run`으로 시험할 때는 `--state-file <임시경로>`를 주자.** 안 주면 시험한 만큼 "받았다"고 기록돼 진짜 첫 수집에서 그 리뷰들이 빠진다.

## 시험 결과 (2026-11-23)
- 단위 테스트 14개 통과 (원본 유지, 실패 건너뛰기, Retry-After·재시도 포기, 종류별 간격, 오류에 쿼리 없음, 최초 수집 페이징, 증분 멈춤, 새 리뷰 없음, 같은 초 리뷰, 상한, cursor 반복, 한 게임 실패, 상태 저장, CSV).
- 실제 호출 `--limit 3`: 사양 3/3, 동접자 3/3 성공. 리뷰 2게임 × 250건 → 500건(3페이지씩), **두 번째 실행은 새 리뷰 0건·1페이지**로 증분이 동작했다. (이 시험은 페이지 단위 봉투였을 때의 것이다. 한 건 단위로 바꾼 뒤에는 1게임 × 5건으로 5개 봉투가 나오는 것을 확인했다.)
- 정제기 호환: 사양 3건 모두 `refined.requirements` 1행(unmatched 0), 동접자 3건 모두 `refined.player_counts` 1행(unmatched 0).

## 아직 안 한 것
- **`owned_games`(사용자 보유 게임·업적, ④).** 사용자가 연동할 때 Backend가 요청하는 흐름이라 수집기 단독으로 만들 수 없다. 요청을 받는 방식(Backend → Kafka 요청 토픽? 직접 호출?)부터 정해야 한다.
- 리뷰 상한 · 수정·삭제 리뷰 처리 (위 참고), Kafka 실제 전송 시험·전송 실패 감지·스케줄 (`igdb.md`와 같다).
- **계약 문서와 어긋난다.** `docs/contracts/messages/raw.steam.json`의 review 예시는 페이지 단위(`reviews[]`)다. 수집기를 한 건 단위로 바꿨으므로 계약 예시도 바꿔야 한다 (`shared/`·`docs/contracts/` 변경은 별도 PR, `open-questions.md` 5번).
- **리뷰 수·긍정 비율을 어디서 받을지.** 페이지 단위의 `query_summary`를 더 이상 보내지 않는다. 화면용 `review_count_ko`·`positive_pct`는 원래 `GetItems` 요약을 쓰기로 했는데(`steam-notes.md` 2·3절) 이 수집기는 아직 `GetItems`를 호출하지 않는다 (`open-questions.md` 10번).
