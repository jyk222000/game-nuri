# 수집 필드 → 테이블 컬럼 매핑표

「겜누리 최종 기능 명세」(2026-11-19)의 MariaDB·MongoDB 테이블이 필요로 하는 컬럼과, 수집 테스트(`scripts/check_candidates.py`, `scripts/check_gaps.py`, 후보 15개)로 확인한 필드를 연결한 표. 갱신: 2026-11-20.
컬럼 이름은 제안이며 ERD 확정 때 조정한다. 상태: ✅ 확인됨, ⚠️ 부분/조건부, ❌ 불가, ❓ 미확인.
세부 근거: [itad-notes.md](itad-notes.md), [steam-notes.md](steam-notes.md), [danawa-notes.md](danawa-notes.md).

## 0. 기능별 한눈에 보기
| 기능 | 수집 데이터로 채울 수 있나 | 남은 문제 |
|---|---|---|
| ① 가격 비교 | ✅ PC는 ITAD(KRW), 콘솔은 다나와 | 다나와 이름 매칭·분류가 규칙 기반(오분류 가능), 이상값은 표시만 함 |
| ② 구매 타이밍·할인 예측 | ⚠️ 이력은 ITAD `history/v2` + 역대 최저가(KRW) | 이력 시계열이 USD(환율 필요). 다나와 자체 "할인 이력"은 수집 불가 → 우리가 쌓는 스냅샷으로 대체 |
| ③ 목표가 알림 | ✅ 현재가·이력 | 주기 수집이 전제 |
| ④ 플레이 성향 | ✅ 클리어 시간 ✅ 개인 데이터 | 보유 게임·플레이타임·업적은 공개 프로필이면 수집됨(개인 계정으로 확인). 친구 목록은 명세에 쓸 곳이 없어 제외 |
| ⑤ 리뷰 AI 요약 | ⚠️ Steam 한국어 리뷰 본문 ✅ | 본문 출처는 **Steam 하나**(다나와 리뷰는 robots.txt 금지). 전체 수집량·증분 방식·한도 미확정 |
| ⑥ PC 사양 | ✅ Steam `pc_requirements` | 사양 HTML 파싱은 정제 몫 |
| ⑦ 동접자 | ✅ Steam 현재 접속자 | 주기 수집해 추이 저장 |
| ⑧ 구글 로그인 · ⑨ 실시간 검색어 · ⑩ API 순위 | 수집 대상 아님 | 서비스 설계 |

## 1. 게임 (`games`, 검색·상세·필터) — raw.igdb, raw.steam, raw.price
| 컬럼 | 출처 필드 | 기능 | 상태 |
|---|---|---|---|
| `igdb_id` (기준 키) | IGDB `games.id` | 공통 | ✅ |
| `name_en` / `name_ko` | IGDB `name` / `game_localizations`(region=Korea) | 검색·자동완성 | ✅ ko는 있으면. 후보 표기와 IGDB 한국어 이름이 다른 경우가 있다(잇 테이크스 투 ↔ 잇 테이크 투, 헬다이버즈 2 ↔ 헬다이버스 2) |
| `aliases` | IGDB `alternative_names` 중 한국어 약칭("사펑", "레데리2")·영문 표기 변형 (`igdb_aliases()` 규칙으로 선별) + 사람이 검수한 LLM 표기 후보(Gemini, danawa-notes 14절) | 검색·다나와 매칭·엘라스틱서치 동의어 | ✅ IGDB 자동 / ⚠️ LLM 표기는 검수 필요(판매자 표기 `백 포 블러드`, `스타듀벨리`는 수동) |
| `series_ids` (또는 `collection_ids`) | IGDB `collections`, `franchises` + 같은 시리즈 게임 목록 | 상품 배정·제외 규칙 자동 생성 | ✅ 시험 완료(danawa-notes 12·15절) |
| `slug`, `summary`, `first_release_date`, `game_type` | IGDB 동명 필드 | 상세 | ✅ |
| `platforms` | IGDB `platforms.name` → 내부 키(PS5/PS4/Switch/Switch2/XboxSeries/XboxOne/PC) | ①, 필터 | ✅ |
| `genres`, `themes`, `game_modes`, `player_perspectives`, `keywords` | IGDB `*.name` (영어) | 필터 `/api/genres`, `/api/tags` | ✅ 한국어 이름은 매핑표 필요 |
| `cover_image_id` | IGDB `cover.image_id` (URL은 규칙으로 조합) | 상세 | ✅ |
| `developers`, `publishers` | IGDB `involved_companies` / Steam `developers`, `publishers` | 상세 | ✅ |
| `age_rating` | IGDB `age_ratings` / Steam `required_age` | 상세 | ✅ |
| `rating`, `rating_count` | IGDB `total_rating`, `total_rating_count` | 상세 | ✅ |
| `parent_game_id`, `version_parent_id` | IGDB `parent_game`, `version_parent` (+ `dlcs`, `expansions`, `remakes`, `remasters`, `bundles`) | 에디션·DLC 분류 | ✅ |
| `korean_supported` | Steam appdetails `supported_languages` | 필터·상세 | ✅ 파싱 필요 |
| `steam_genres`, `steam_categories` | Steam appdetails `genres`, `categories` (한국어) | 필터·온라인 여부(⑦) | ✅ |
| `header_image`, `short_description`, `release_date` | Steam appdetails | 상세(대체 이미지·설명) | ✅ |
| `tags` | ITAD `games/info/v2` `tags` | 필터 | ✅ |
| `dlc_appids` | Steam appdetails `dlc` | 에디션·DLC 분류 | ✅ |

## 2. 게임 외부 ID (`game_external_ids`) — 게임 ID 통합(IGDB 기준)
| 컬럼 | 출처 | 상태 |
|---|---|---|
| `steam_appid` | IGDB `external_games`(Steam source)의 `uid` | ✅ 15/15 |
| `itad_id` (UUID) | ITAD `lookup/v1?appid=<숫자>` (`app/` 접두사를 붙이면 항상 실패) | ✅ 15/15, 바이오하자드 4는 `resident-evil-4-2023` |
| 다른 스토어 ID(Epic·GOG 등) | IGDB `external_games`의 `uid`, `url`, 소스 | ⚠️ 스토어별 소스 값 확인 필요 |
| 다나와 `pcode` (플랫폼·매체·상태별 여러 개) | 다나와 카탈로그 `productSeq` | ⚠️ IGDB ID와의 연결은 이름 매칭(`names`·`aliases`·`danawa_exclude`) |

## 3. 가격 최신 (`prices_current`) ①③ — raw.price, raw.console
공통 컬럼: `game_id`, `source`(itad/danawa/steam), `store`, `platform`, `medium`(DL/PKG/코드), `condition`(new/used), `price_krw`, `regular_krw`, `cut`, `collected_at`.

| 출처 | 필드 → 컬럼 | 상태 |
|---|---|---|
| ITAD `games/prices/v3?country=KR` (POST) | `deals[].shop` → `store`, `price.amount`(KRW) → `price_krw`, `regular` → `regular_krw`, `cut`, `drm`, `platforms`, `timestamp`, `expiry`, `url`, `storeLow`, `historyLow`(전체·1년·3개월) | ✅ KRW로 바로 옴. 한국 기준 판매처는 적다(엘든 링 2곳) |
| Steam appdetails `price_overview` (cc=kr) | `final`, `initial`(×100 단위), `discount_percent`, `currency=KRW` | ✅ ITAD와 교차 검증용 |
| 다나와 카탈로그 상품 | `minPrice` → `price_krw`, `shopCount`, `bundleName`에서 파싱한 `platform`·`medium`·`condition`, `initialPrice`(출시가), `pcode` | ✅ |
| 다나와 개별 판매처 상품 | `minPrice`, `shop`, `post_price`(배송비), `posted`, `listing_id`, 제목에서 파싱한 `platform`·`condition`·`region_lang` | ✅ 카테고리 코드(c1=1393)로 게임 판별. 제목 파싱은 오분류 가능 |
| 다나와 파생 필드 | `is_base`, `edition_tokens`, `region_lang`(ko/import), `flags`(single_source·few_shops·new_vs_used), `source`(catalog/shop_listing), `found_via` | ✅ 규칙 기반 |
| 다나와 판매처별 가격표 (상세 페이지 정적 HTML) | `shopTableRows`: `logo`, `price`, `deliveryPrice`, `isLowest`, `linkProductCode` (10개), `benefitRows` 혜택가 | ⚠️ 가능하나 검색 `minPrice`에 더해 얻는 정보가 적다(판매처별·배송비). 요청 수가 크게 늘어 기본 수집에서는 제외 |

다나와 플랫폼별 최저가는 본편·국내판 기준 `플랫폼 × 신품/중고` 칸으로 저장하고, 에디션은 `edition`, 해외판은 `import`에 따로 둔다(본편 값이 없는 칸에만 에디션을 대체 표시). 칸별 `flags`와 출처가 같이 간다. 상세: danawa-notes 6~8절.

## 4. 가격 이력 (`price_history`) ①②
| 컬럼 | 출처 | 상태 |
|---|---|---|
| `game_id`, `store`, `ts`, `price`, `regular`, `cut`, **`currency`** | ITAD `games/history/v2` `timestamp`, `shop`, `deal.price`, `deal.regular`, `deal.cut` | ✅ **가격은 USD만**(`country`·`currency` 파라미터 무시). 원본 USD 그대로 저장, 원화 환산은 정제에서 |
| 콘솔 이력 | 우리가 6시간마다 쌓는 다나와 스냅샷 | ⚠️ 다나와 자체 "할인 이력"은 수집 불가(정적 HTML에 없고, 화면이 부르는 `/api/proxy/…`는 robots.txt 금지) |

## 5. 최저가·할인 목록·환율 (API 12~14)
| 대상 | 출처 | 상태 |
|---|---|---|
| 역대 최저가 | ITAD `historylow/v1`(KRW, 일시·판매처), `prices/v3`의 `historyLow` | ✅ |
| 스토어별 최저가 | ITAD `storelow/v2` (POST, KRW) | ✅ |
| 할인 중 목록 | ITAD `deals/v2` (KRW) | ✅ |
| 환율(`exchange_rates`) | 수집 출처 없음 | ❓ 정제 담당이 출처 결정. 현재 환율 vs 날짜별 환율(이력 정확도) |
| 판매처 목록(`stores`) | ITAD `service/shops/v1?country=KR` (35곳) | ✅ "PC 스토어 8곳"은 여기서 선정(정책 결정 필요) |

## 6. 사양 (`game_requirements`) ⑥ — raw.steam → refined.requirements
| 컬럼 | 출처 | 상태 |
|---|---|---|
| `appid`, `min_html`, `rec_html` | Steam appdetails `pc_requirements.minimum` / `.recommended` | ✅ 15/15, 스타듀 밸리는 min만 |
| `mac_*`, `linux_*` | `mac_requirements`, `linux_requirements` | ✅ (선택) |
| `cpu`, `gpu`, `ram`, `storage` 등 파싱 값 | HTML 정제 | ❓ 정제 단계 몫 |

## 7. 리뷰 (`reviews` Mongo/ES, `review_summaries`) ⑤
| 컬럼 | 출처 | 상태 |
|---|---|---|
| `review_count_ko`, `positive_pct`, `label` (화면용, Steam 구매 기준) | Steam `IStoreBrowseService/GetItems` `reviews.summary_language_specific` (= `GetAppReviews` `purchase_type=0`) | ✅ 15/15, 스토어 표시와 일치 |
| `review_count_all` | `summary_filtered` | ✅ |
| `review_count_ko_all` (외부 구매 포함) | `GetAppReviews` `purchase_type=1`의 `query_summary.total_reviews`, 또는 수집 본문의 `steam_purchase`로 집계 | ✅ 차이 원인: steam-notes 2절 |
| 외부 평점(Steam·Metascore·Metacritic 유저·OpenCritic) | ITAD `games/info/v2` `reviews` | ✅ |
| **리뷰 본문**: `recommendationid`(PK), `review`, `voted_up`, `votes_up`, `votes_funny`, `weighted_vote_score`, `timestamp_created`, `timestamp_updated`, `language`, `author.playtime_at_review`, `author.playtime_forever`, `steam_purchase`, `received_for_free`, `written_during_early_access`, `refunded`, `hardware` | Steam `IUserReviewsService/GetAppReviews` (`languages=["koreana"]`, `purchase_type=1`) | ✅ 15/15, 후보당 한국어 본문. 옛 `store…/appreviews`는 폐기 |
| 다나와 리뷰·주제어 | `/api/proxy/pas/v1_0/service/companyProductReview/link/product.json` 등 | ❌ robots.txt `Disallow: /api/` |
| `keywords`, `ai_summary` | ES 집계·AI 산출물 | 서비스 산출물 |

수집 방식 메모(steam-notes 5·6절):
- 최초 1회 전체 수집(15개 후보 ≈ 23만 건, 약 2시간, 원본 약 190MB). `cursor`를 따라 0건 페이지에서 종료.
- 이후 매일 증분: 최신순으로 받다가 아는 `recommendationid`를 만나면 중단. 수정 리뷰는 갱신순(`filter=2`)이 별도로 필요. 증분은 시뮬레이션만 확인(실제 새 리뷰 시험은 하루 뒤).
- `received_for_free`, `refunded` 리뷰를 키워드 분석에서 뺄지는 미정.
- 호출 한도(429 시점)는 못 찾음(0.2초 간격 20회까지 정상).

## 8. 동접자 (`player_counts`) ⑦
| 컬럼 | 출처 | 상태 |
|---|---|---|
| `appid`, `collected_at`, `player_count` | Steam `ISteamUserStats/GetNumberOfCurrentPlayers` (키 불필요) | ✅ 주기 수집해 추이를 만든다 |
| 참고: 최근·일·주·역대 최고 | ITAD info `players` | ✅ (일부 게임은 null) |
| `is_online` (온라인 게임 여부) | Steam `categories`(멀티플레이어 등) | ✅ 파생 |

## 9. 플레이 성향 ④
| 컬럼 | 출처 | 상태 |
|---|---|---|
| `ttb_hastily`, `ttb_normally`, `ttb_completely`, `ttb_count` (초 단위, 없으면 null) | IGDB `game_time_to_beats` | ✅ 15/15 (헬다이버즈 2는 `completely`만, count 1) |
| 사용자 식별 | `ResolveVanityURL`(vanity→SteamID64), `GetPlayerSummaries`(닉네임·국가·가입 시각·공개 상태 `communityvisibilitystate`) | ✅ 키 필요 |
| 보유 게임·플레이타임 | `GetOwnedGames`(`include_appinfo=1`): `appid`, `name`, `playtime_forever`, 플랫폼별 플레이 시간(windows/mac/linux/deck), `rtime_last_played`, `has_community_visible_stats` | ✅ 71개 수신. 플레이 이력 56개 |
| 최근 2주 플레이 | `GetRecentlyPlayedGames` | ✅ 호출 성공(해당 계정은 0건) |
| 사용자 레벨 | `GetSteamLevel` | ✅ |
| 사용자별 업적 | `GetPlayerAchievements`(`appid`별 1회) | ✅ GTA V 77개 중 31개 달성. 업적 조회 가능 게임 63/71 |
| 친구 목록 | `GetFriendList` | ➖ 불필요(명세에 사용처 없음). 시험 계정이 친구 목록을 비공개로 둬 401 |
| 공개 범위 조건 | 프로필과 게임 상세가 모두 공개여야 `GetOwnedGames`가 채워짐. 비공개는 빈 응답 | ⚠️ 연동 시 공개 설정 안내 필요 |
| 게임별 업적 목록·전체 달성률 | `GetSchemaForGame`(ko 이름·숨김 여부), `GetGlobalAchievementPercentagesForApp` | ✅ |

## 10. 수집과 무관한 서비스 테이블 (앱 설계에서 정의)
`users`, `wishlist`, `alerts`(목표가), `alert_logs`, `notification_settings`, `user_specs`, `review_summaries`(산출물), 사양 적합도 판정 결과, 클릭스트림, API 사용 지표. 수집 데이터와는 `game_id`(IGDB ID)로만 연결된다.

## 11. 수집 주기와 호출량
| 출처 | 명세 주기 | 후보 15개 기준 실측 | 비고 |
|---|---|---|---|
| ITAD | 6시간 | 게임당 호출 몇 회 | 5분 1,000회 한도에 여유 |
| IGDB | 매일 | 게임당 호출 몇 회, 0.3초 간격 | 초당 4회 한도 |
| Steam 사양·요약 | 매일 | 게임당 호출 몇 회, 1.5초 간격 | 키 불필요 |
| Steam 리뷰 본문 | 매일 | 최초 약 2시간, 이후 증분 게임당 1~3페이지 | 한도 미확인 |
| Steam 동접자 | 1시간 | 게임당 1회 | 키 불필요 |
| 다나와 | 6시간 | 기본 15건 + 빈 플랫폼 보강 47건 ≈ 62건 × 10초 ≈ 10분 | robots.txt `Crawl-delay: 10` |

- **명세의 "다나와 요청 간격 3초 이상"은 robots.txt와 어긋난다**(`Crawl-delay: 10`). 명세를 10초로 고치는 것이 맞다.
- 게임 수 N에 대해 다나와 요청 ≈ 4N건(기본 1 + 보강 평균 3) × 10초. N=300이면 약 3.3시간이라 6시간 주기에 들어가지만 여유가 크지 않다.

## 12. 남은 공백
1. **⑤ 리뷰 본문 수집량 결정**: 게임당 몇 건이 필요한지(전체 vs 최근 N건 vs 도움됨 순), 증분의 실제 시험(하루 뒤), 호출 한도.
2. **다나와 리뷰·할인 이력** (❌): 수집 불가. 명세 ⑤의 다나와 리뷰 출처와 ①·②의 다나와 "할인 이력"은 바꾸거나 뺀다.
3. **Steam 개인 데이터(④)** (✅): 확인 완료(`scripts/check_steam_user.py`, 샘플 `samples/check_steam_user/`). 친구 목록은 명세에 쓸 곳이 없어 시험하지 않았다. 남은 것은 비공개 프로필 대응 정책. 한 계정만 시험했고 후보 15개와 겹치는 게임은 2개(RDR2, 잇 테이크스 투)뿐이다.
4. **환율 출처** (❓): `history/v2`가 USD라 정제에서 결정.
5. **PC 스토어 8곳 선정**: ITAD 35곳 중 고르는 정책 결정.
6. **다나와 ↔ IGDB 연결**: 이름 매칭에 의존한다. 자동화 시험 결과(danawa-notes 5·12~15절): 제외 규칙은 IGDB 시리즈로 자동 생성하고 수동은 예외만, 별칭은 IGDB 한국어 이름 + 검수한 LLM 표기. 엘라스틱서치 도입 때는 "시리즈를 함께 색인해 배정"으로 옮긴다. 남은 것: 원작·리메이크 구분(출시 연도·플랫폼을 색인에 넣을 것), 한글·영문 점수 보정(숫자 토큰 정확 일치), 상품 배정을 수집과 정제 중 어디서 하는지 팀 확인, Gemini 키 관리와 검수 절차.
7. **해외판 처리 규칙**: 지금은 별도 열로만 둠. 최종 제외 여부 미정.
8. **IGDB 장르·테마 한국어 이름 매핑표**.
9. **다나와 검색 범위**: 1페이지(40건)만 받는다. 2페이지 이후는 본편 국내 가격을 바꾸지 못해 제외(danawa-notes 10절, 위쳐 3 한 게임 근거).
