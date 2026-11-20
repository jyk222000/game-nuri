# Steam 수집 알아둘 점

`scripts/check_candidates.py`, `scripts/check_gaps.py`로 확인한 내용. 기준일: 2026-11-20.

## 1. 리뷰 본문: `IUserReviewsService/GetAppReviews` (옛 `appreviews`는 폐기)
- **옛 방식(`store.steampowered.com/appreviews/<appid>?json=1`)은 DEPRECATED**이고 이 환경에서 스토어 홈으로 302 된다. 키를 붙이거나 헤더를 바꿔도 같았다. 처음 Steam 리뷰가 실패한 원인은 이 폐기된 주소를 쓴 것이었다(사용자가 새 방식을 알려 줌).
- **새 방식:** `GET https://api.steampowered.com/IUserReviewsService/GetAppReviews/v1/`
  - 파라미터는 `input_json`(JSON 문자열)에 담는다. 예: `{"appid":1245620,"languages":["koreana"],"filter":1,"purchase_type":1,"review_type":0,"num_per_page":20}`
  - 키(`key`)는 **선택**이다. 키 없이도 되고, 앱 연동 키면 호출 한도만 높다. 한도 초과는 HTTP 429. 키 없는 응답은 최대 10분 캐시.
  - `languages`가 비면 **영어가 기본**이다. 한국어는 `["koreana"]`를 명시한다. `"all"`은 전 언어.
  - 응답에 `success` 필드가 없다. **HTTP 상태로 판단**한다.
  - 1페이지는 `num_per_page` 최대 100. 다음 페이지는 응답의 `cursor`(URL 인코딩)를 `cursor`로 넘긴다. 첫 페이지는 `*` 또는 생략.
- 주요 파라미터: `filter`(0 도움됨/1 최신/2 갱신/3 재미), `review_type`(0 전체/1 긍정/2 부정), `purchase_type`(0 Steam 구매만/1 전체/2 외부 구매), `day_range`(도움됨 정렬에서만, 기본 30·최대 365·0은 무제한), `filter_offtopic_activity`(기본 true: 리뷰 폭탄 제외), `playtime_min_hours`/`playtime_max_hours`, `date_range_*`, `use_review_quality`.
- 응답: 최상위 `query_summary`(`num_reviews`, 첫 페이지·전체 타입일 때만 `review_score`, `review_score_desc`, `total_positive`, `total_negative`, `total_reviews`), `reviews[]`, `cursor`, `total_matching`, `day_range_used`.
- 리뷰 필드: `recommendationid`, `language`, `review`(본문), `timestamp_created`, `timestamp_updated`, `voted_up`, `votes_up`, `votes_funny`, `weighted_vote_score`(숫자), `comment_count`, `steam_purchase`, `received_for_free`, `written_during_early_access`, `refunded`, `primarily_steam_deck`, `hardware`(`os`, `cpu_name`, `adapter_description`, `system_ram`, `vram_size`), `author`(`steamid`, `num_reviews`, `playtime_forever`, `playtime_last_two_weeks`, `playtime_at_review`, `last_played`; 분 단위).
- 옛 API와 차이: `language`→`languages`(배열), `author.num_games_owned` 삭제, `weighted_vote_score`는 문자열이 아니라 숫자, `refunded` 추가, `hardware` 문자열은 욕설 필터가 없다.
- 15개 후보 결과: 한국어 리뷰 본문 15/15 수집(후보당 최신 20건), 모두 `cursor` 있음(다음 페이지 가능). 한국어 리뷰 총건수 2,966건(백 4 블러드)~36,212건(스타듀 밸리). 원본은 `samples/check_candidates/steam/NN_*_reviews_text.json`.
- ⑤ 요약에 쓰는 전체 수집량(페이징으로 몇 건까지 받을지)과 호출 한도는 아직 시험하지 않았다. 게임당 1만 건 이상인 경우가 많아 `num_per_page=100` 기준 100회 이상이다.

## 2. 한국어 리뷰 총건수가 호출마다 다른 이유 (원인 확인함)
**원인: 구매 유형(`purchase_type`)이 다르다.** `IStoreBrowseService/GetItems`의 한국어 요약은 **Steam에서 구매한 사용자의 리뷰만** 센 값이고, `GetAppReviews`를 `purchase_type=1`(전체)로 부르면 키 활성화·외부 구매 리뷰가 더해진다. 2026-11-20, 총건수(`query_summary.total_reviews`) 비교:

| 조건 | 몬스터 헌터 월드 | 엘든 링 | 헬다이버즈 2 |
|---|---|---|---|
| `GetItems` 한국어 요약 | 21,695 | 25,880 | 15,065 |
| `GetAppReviews` 한국어, `purchase_type=0`(Steam 구매만) | **21,693** | **25,881** | **15,058** |
| 한국어, `purchase_type=1`(전체) | 34,512 | 28,135 | 18,951 |
| 한국어, `purchase_type=2`(외부 구매만) | 12,819 | 2,256 | 3,893 |
| 한국어, `purchase_type=0` + 리뷰 폭탄 포함 | 21,801 | 25,881 | 15,058 |
| 전 언어, `purchase_type=0` | 319,527 | 836,030 | 856,619 |
| 전 언어, `purchase_type=1` | 521,081 | 1,162,600 | 1,190,921 |

- `GetItems` 요약 ≈ `purchase_type=0`(수 건 차이는 호출 시점의 차이). 전 언어 요약(`summary_filtered`)도 `purchase_type=0`과 같다(몬스터 헌터 월드 319,640 vs 319,527).
- **리뷰 폭탄 필터(`filter_offtopic_activity`)의 영향은 작다**(몬스터 헌터 월드 +108건, 나머지 0~2건). 기본값(true) 그대로 둔다.
- 몬스터 헌터 월드는 외부 구매 리뷰가 전체의 37%(12,819/34,512)라 차이가 크다. 엘든 링은 8%.
- **리뷰마다 `steam_purchase` 필드가 있다.** 백 4 블러드에서 `purchase_type=1`로 받은 2,964건 중 `steam_purchase=true`는 2,379건이고, `purchase_type=0` 직접 조회는 2,381건이다. 한 번 전체로 받고 필드로 거르면 Steam 구매 기준을 다시 만들 수 있다(차이 2건은 숨김·삭제로 보임). 긍정 비율도 55%로 같다(전체 54%).
- 참고(백 4 블러드, 수집분): `received_for_free` 43건, `refunded` 44건, `written_during_early_access` 0건.

### 결정
| 용도 | 기준 | 이유 |
|---|---|---|
| 화면에 보이는 **한국어 리뷰 수·긍정 비율** | **Steam 구매 기준**(`purchase_type=0` 또는 `GetItems` 요약) | Steam 스토어에 표시되는 값과 일치한다. 사용자가 스토어와 비교해도 어긋나지 않는다. |
| ES **키워드 추출용 본문** | **`purchase_type=1`(전체)**로 받음 | 데이터가 더 많다. 각 리뷰의 `steam_purchase`, `received_for_free`로 나중에 거를 수 있어 호출을 두 번 하지 않는다. |
- 건수 필드 이름은 구분해서 저장한다: `review_count_ko`(Steam 구매 기준, 화면용), `review_count_ko_all`(외부 구매 포함).
- 호출을 아끼려면 `GetItems`(요약, 한 호출에 여러 게임 가능)로 화면용 값을 받고, 본문 수집은 별도로 한다.
- 이 결정은 팀이 정할 수 있는 기본안이다. 외부 구매 리뷰를 화면 수치에 넣고 싶으면 `review_count_ko_all`을 쓰면 된다.

## 3. 리뷰 요약만 필요할 때: `IStoreBrowseService/GetItems`
- `GET https://api.steampowered.com/IStoreBrowseService/GetItems/v1/`, `input_json`에 `{"ids":[{"appid":…}],"context":{"language":"koreana","country_code":"KR"},"data_request":{"include_reviews":true}}`. 키 불필요.
- `reviews.summary_language_specific`(한국어)·`summary_filtered`(전체)의 `review_count`, `percent_positive`, `review_score`, `review_score_label`. 본문은 없다.

## 4. 그 밖에 확인한 Steam 호출
- `appdetails`(`cc=kr`, `l=koreana`): 사양(`pc_requirements`), 장르·카테고리(한국어), `supported_languages`, `price_overview`(KRW, 값은 ×100 단위), `dlc`, `release_date` 등. 키 불필요.
- `ISteamUserStats/GetNumberOfCurrentPlayers`(키 불필요), `GetGlobalAchievementPercentagesForApp`, `GetSchemaForGame`(키, 한국어 업적 이름).
- 공개된 API 목록(`ISteamWebAPIUtil/GetSupportedAPIList`)에는 `IUserReviewsService`, `IStoreBrowseService`가 보이지 않는다. **문서에 있는 API가 이 목록에 없을 수 있다.**
- 보유 게임·플레이타임·유저 업적은 공개 프로필 SteamID가 필요해 시험하지 않았다.

## 5. 리뷰 페이징 시험 (2026-11-20, 백 4 블러드 한국어 전체)
`GetAppReviews`를 `filter=1`(최신순), `num_per_page=100`, `purchase_type=1`, `languages=["koreana"]`로 `cursor`를 이어 끝까지 받았다. 원본은 `samples/check_candidates/steam/paging_back4blood_reviews.json`(2.46MB).

| 항목 | 결과 |
|---|---|
| 페이지 수 | 31 (마지막은 0건) |
| 받은 리뷰 | 2,964건 (첫 페이지 `total_matching` 2,966건) |
| 중복 | 0 (`recommendationid` 기준 고유 2,964) |
| 정렬 | 최신순 유지, 가장 오래된 리뷰 2021-10-12 |
| 본문 | 2,957건이 비어 있지 않음, 평균 114자 |
| 소요 | 45초 (요청 간격 1.5초 + 응답 약 1.4초) |
| 연속 호출 | 간격 0.2초로 키 없이 20회 연속 모두 200, **429 없음** |

### 알아둘 점
- **끝 판정은 `cursor`가 아니라 "0건 페이지"다.** 마지막 페이지(0건)에서도 `cursor`가 계속 온다. 반복 종료 조건은 `reviews`가 비었을 때로 한다(`cursor` 없음이나 같은 값 반복은 안전장치로 함께 검사).
- **2건이 총건수보다 적다.** 100건 요청에서 두 페이지가 99건을 돌려줬다(1·18페이지). 삭제·숨김 처리로 보이며, 원인은 확인하지 못했다. 총건수와 정확히 일치한다고 가정하면 안 된다.
- 응답 시간은 약 1.2~1.9초로 호출마다 비슷하다. 키 없는 호출의 한도(429 시점)는 이번 시험으로는 찾지 못했다(0.2초 간격 20회까지 문제 없음). 더 많은 호출에서의 한도는 모른다.
- `query_summary`(점수, `total_positive`, `total_negative`)는 첫 페이지에만 온다.

### 전체 수집량 추정 (15개 후보)
- 한국어 리뷰 총건수 합계는 약 23만 건(2,966건~36,212건)이다. 100건 단위 약 2,300페이지, 호출당 약 3초(간격+응답)면 **약 2시간**이다. 용량은 리뷰당 약 830B로 계산하면 원본 JSON 약 190MB다.
- 매일 전체를 다시 받을 필요는 없다. `filter=1`(최신순)로 받다가 지난번 수집 시각(`timestamp_created`)이나 알려진 `recommendationid`에 닿으면 멈추는 **증분 수집**이 맞다. 수정된 리뷰까지 반영하려면 `filter=2`(갱신순)로 같은 방식. 이 증분 방식은 구현·시험하지 않았다.
- ⑤ 요약(ES 키워드 TOP 10)에 게임당 몇 건이 필요한지가 정해지지 않았다. 최근 N건이나 도움됨(`filter=0`)만으로 충분한지는 팀이 정할 일이다.

## 6. 증분 수집 시험 (2026-11-20, 백 4 블러드, 시뮬레이션)
새 리뷰가 올라와야 진짜 시험이 가능하므로, 방금 받은 전체 스냅샷(2,964건)에서 **최신 150건을 일부러 빼서 "아직 모르는 새 리뷰"로 취급**하고 실제 API에 증분 수집을 돌렸다. (수집 직후라 실제로 새로 올라온 리뷰는 없었다.)

알고리즘: `filter=1`(최신순)로 `cursor`를 따라 받으면서, **이미 아는 `recommendationid`를 만나면 그 페이지까지만 받고 멈춘다.** 새 리뷰는 아는 리뷰보다 앞에 오므로(`timestamp_created` 내림차순) 경계 전까지가 새 리뷰다.

| 시험 | 결과 |
|---|---|
| 뺀 150건 찾기 | **150건 모두 찾음**, 못 찾은 것 0건, 중복 없음 |
| 요청 수 | 2페이지 (경계가 2페이지째에 있음). 전체 수집은 31페이지 |
| 전부 아는 상태로 재실행 | **1페이지, 새 리뷰 0건**에서 종료 |
| 갱신순(`filter=2`) | 1페이지 99건, `timestamp_updated` 내림차순. 이 중 `updated > created`인 수정 리뷰 37건 |
| 스냅샷 이후 수정된 리뷰 | 0건 (수집 직후라 수정이 없었다) |

### 한계 (확인하지 못한 것)
- **실제로 새 리뷰가 올라오는 상황은 시험하지 못했다.** 150건 취급은 "아는 목록에서 뺀 것"이라, 새 리뷰의 정렬·지연·삭제 같은 실제 변화는 반영하지 못한다. 하루 뒤 같은 스냅샷으로 다시 돌려서(새 리뷰 수 = 실제 증가량) 확인하는 게 진짜 시험이다. 후보 중 리뷰가 자주 달리는 게임(엘든 링 등)이 더 낫다.
- **수정된 리뷰는 최신순으로는 잡히지 않는다.** `timestamp_created`가 그대로라 위치가 바뀌지 않는다. 수정(작성자가 추천/비추천이나 본문을 고침)을 반영하려면 `filter=2`(갱신순)로 받으면서, 아는 리뷰의 `timestamp_updated`가 더 크면 갱신하는 별도 경로가 필요하다. 이 경로의 실제 동작은 시험하지 못했다(수정이 없었음).
- 삭제된 리뷰는 알 수 없다. 총건수가 줄어드는 것(`total_matching`)으로만 짐작할 수 있다. 삭제 반영 방식은 정하지 않았다.
- 멈춤 조건이 "아는 id 1건 만남"이다. 그 id가 우연히 그 사이 삭제됐으면 경계를 못 만나고 다음 아는 id까지 더 받게 되지만 오류는 아니다. 페이지 상한(`max_pages`)을 안전장치로 둔다.
- 코드는 시험용 임시 스크립트다. 프로젝트 스크립트로 옮기지 않았다.

### 정리
- 매일 수집: ① 최신순 증분(새 리뷰) ② 갱신순 1~2페이지(수정 리뷰, 아는 id의 `timestamp_updated` 비교). 둘 다 1~3페이지면 끝나서 게임당 호출 수가 작다.
- 최초 1회는 전체 수집(15개 후보 약 2시간, 5절).

## 7. 개인 데이터(명세 ④) 시험 (2026-11-20)
스크립트 `scripts/check_steam_user.py`, 샘플 `samples/check_steam_user/`. 사용자가 제공한 공개 프로필 1개로 시험했다. 키는 `.env`의 `STEAM_API_KEY`.
**샘플에는 SteamID와 닉네임 같은 개인 정보가 있으니 저장소·공유 자료에 올리지 않는다.**

| 호출 | 결과 | 얻는 것 |
|---|---|---|
| `ISteamUser/ResolveVanityURL` | ✅ | vanity ID → SteamID64 |
| `ISteamUser/GetPlayerSummaries` | ✅ 프로필 공개(`communityvisibilitystate`=3) | 닉네임, 국가, 가입 시각, 아바타 |
| `IPlayerService/GetOwnedGames` (`include_appinfo=1`) | ✅ 71개 | `appid`, 이름, 총 플레이 시간, 플랫폼별 플레이 시간(Windows·Mac·Linux·Deck), `rtime_last_played`, `has_community_visible_stats` |
| `IPlayerService/GetRecentlyPlayedGames` | ✅ 0건(최근 2주 플레이 없음) | 최근 플레이 |
| `IPlayerService/GetSteamLevel` | ✅ | 레벨 |
| `ISteamUserStats/GetPlayerAchievements` | ✅ GTA V 77개 중 31개 달성 | 게임별 업적(`appid` 1건당 1회 호출) |
| `ISteamUser/GetFriendList` | ❌ 401(친구 비공개) | 명세에 쓸 곳이 없어 시험하지 않음 |

- 보유 71개 중 플레이 이력 56개, 업적 조회 가능 63개. 후보 15개와 겹치는 것은 레드 데드 리뎀션 2와 잇 테이크스 투 2개뿐이다.
- 프로필과 게임 상세가 둘 다 공개여야 `GetOwnedGames`가 채워진다. 비공개면 빈 응답이다. 서비스 연동에 공개 설정 안내와 비공개일 때의 표시 정책이 필요하다.
