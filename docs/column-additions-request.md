# column-mapping에 추가를 요청할 컬럼

> 기준일: 2026-11-21.
> **비교 대상:** `docs/collector-test/column-mapping.md`(2026-11-20)의 컬럼 목록 ↔ 수집 시험 코드(`collector/experiments/check_gaps.py` 등)와 수집 노트가 **이미 받고 있는 필드**.
> 수집은 되고 있는데 컬럼 목록에 없는 것만 뽑았다. `column-mapping.md`는 수집 파트 문서라 이 문서는 **요청만** 적는다.
> 쓰는 곳: 분석 번호는 `docs/analysis-feasibility.md`의 번호.

## 요청 컬럼
| # | 제안 컬럼 | 출처 필드 (정확한 이름) | 근거 | 형태·메모 | 분석 | 필수 |
|---|---|---|---|---|---|---|
| 1 | **플랫폼·지역별 출시일** (게임당 여러 행): `game_id`, `platform`, `region`, `released_at`, `released_human` | IGDB `release_dates.platform.name`, `release_dates.region`, `release_dates.date`, `release_dates.human` | `check_gaps.py` 37행(`IGDB_FIELDS_FULL`) | 게임 1개에 플랫폼×지역 행이 여러 개라 한 컬럼에 담을 수 없다(별도 테이블 또는 배열). `date`는 유닉스 초라 UTC로 변환한다. 날짜가 미정이면 `date`는 없고 `human`만 있을 수 있다. 분석에서는 플랫폼별로 가장 이른 날짜를 쓴다 | 7 | ✅ |
| 2 | **평론 점수**: `aggregated_rating` | IGDB `aggregated_rating` | `check_gaps.py` 39행 | 현재 매핑의 `rating`은 `total_rating`(유저+평론 합산)이다. 평론 점수만 따로 필요하다. 평론 점수의 건수(`aggregated_rating_count`)는 **현재 요청 필드에 없어서** 필요하면 요청 필드에도 추가해야 한다 | 3, 7 | ✅ |
| 3 | **외부 평점 컬럼 이름 확정** | ITAD `games/info/v2`의 `reviews` (출처별 점수·건수: Steam, Metascore, Metacritic 유저, OpenCritic) | `itad-notes.md` 3절, `check_gaps.py` 124행 | 매핑 7절에는 "외부 평점"이라는 이름만 있고 컬럼 이름이 없다. 시험 코드는 응답을 통째로 저장만 하고 필드를 풀지 않으므로 **응답 필드 이름은 샘플로 확인이 필요**하다. 출처별로 `source`, `score`, `count` 같은 컬럼으로 풀면 된다 | 3, 7 | ✅ (이름 확정) |
| 4 | 리뷰 `primarily_steam_deck` | Steam `GetAppReviews` 리뷰 필드 `primarily_steam_deck` | `steam-notes.md` 1절 | boolean. 매핑 7절 리뷰 컬럼 목록에 없다. Steam Deck 리뷰의 성능 불만 비교에만 쓰고, 없어도 사양표 신뢰도 표시는 가능하다 | 5 | 선택 |

## 확인이 필요한 점
- **지역 코드.** `check_gaps.py` 215행의 `kr_release`가 `release_dates.region in (5, 8)`을 본다. 제가 아는 IGDB 지역 코드로는 5가 일본, 8이 전 세계, 9가 한국이라 의도한 지역인지 샘플 응답으로 확인이 필요하다(IGDB에 직접 호출해 확인한 것은 아니다).
- **결측.** 평론 점수(`aggregated_rating`)와 외부 평점은 비어 있는 게임이 있을 수 있다. 분석은 결측 게임을 제외하고 표본 수를 함께 표시한다.

## 받고 있지만 요청하지 않는 것 (분석과 무관)
IGDB `screenshots.image_id`, `similar_games.name`, `websites.url`·`websites.type`, `standalone_expansions.name`, `rating`(IGDB 유저 점수만), 리뷰 `comment_count`, `author.num_reviews`, `author.playtime_last_two_weeks`, `author.last_played`.

## 참고: 수집 시험에도 없는 것 (컬럼 추가로 해결되지 않음)
업데이트·뉴스 날짜(Steam `ISteamNews/GetNewsForApp` 시험 필요), DLC 출시일, Steam 판매·인기 차트. 자세한 내용은 `docs/analysis-feasibility.md`의 "컬럼·수집에 요청할 것"과 8번 분석을 본다.
