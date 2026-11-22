# contracts 변경 제안 (ERD 적용 전 확인)

작성: 이고은 (DB 설계·정제) · 2026-11-21 (Kafka·MongoDB 구축 문서 반영)
기준: GitHub main `docs/contracts`, `docs/collector-test/column-mapping.md`, `docs/features.md`, `pipeline/connect/*.json`, MariaDB 구축 문서

`erd.sql`(28개 테이블)은 **지금 메시지 계약을 그대로 지킨 버전**이다. 아래 항목은 메시지·Connector를 먼저 바꿔야 ERD에 넣을 수 있어서 따로 정리했다.

## 1. 다나와 콘솔 가격: 플랫폼·신품/중고 구분 (중요, 기능 ①) — ✅ 11/22 반영 (erd.sql, refined.prices.json, erd_alter_1122.sql)
- **문제**: `refined.prices`의 키는 `game_id, store, edition`(edition = digital | physical | code)뿐이다. 다나와는 같은 게임이 PS5·PS4·Switch × 신품·중고로 나뉘는데(danawa-notes 6~8절), 지금 키로는 서로 덮어쓴다.
- **근거**: column-mapping 3절 공통 컬럼은 `platform`, `medium`, `condition`을 포함한다. 기능 명세 ①은 "다나와 콘솔(DL·PKG·중고 PKG)" 비교다.
- **제안**:
  - `refined.prices`에 `platform`(PC, PS5, PS4, Switch, Switch2, XboxSeries, XboxOne), `condition`(new | used) 필드 추가
  - `prices_current` PK와 `jdbc-sink-prices-current.json`의 `pk.fields`를 `game_id,store,platform,edition,condition`으로 변경
  - `price_history`에도 같은 두 컬럼 추가
  - `condition`이 MariaDB 예약어와 겹치므로 컬럼 이름은 `item_condition`을 제안 (메시지 필드 이름도 같이)
- **영향**: refiner, Kafka Connect(남현식), Backend `GET /api/games/{id}/prices` 응답

## 2. 가격 이상값 표시 (danawa-notes 8절)
- **문제**: 수집은 이상값을 고치지 않고 `flags`(single_source, few_shops, new_vs_used)로 표시만 하는데, 메시지·테이블에 칸이 없다.
- **제안**: `refined.prices`에 `flags`(쉼표 구분 문자열, 선택) 추가, `prices_current`·`price_history`에 `flags VARCHAR(64)` 추가
- **영향**: refiner, Kafka Connect, Backend(화면에 "판매처 1곳" 등 표시)

## 3. 리뷰 수 (steam-notes 2절, 기능 ⑤)
- **문제**: 화면용 한국어 리뷰 수(`review_count_ko`), 외부 구매 포함 수(`review_count_ko_all`), 평가 문구(`review_label`)가 `refined.review_summary`와 `review_summaries`에 없다.
- **제안**: `refined.review_summary`에 세 필드 추가(선택), `review_summaries`에 같은 컬럼 추가
- **영향**: review-summarizer, Kafka Connect, Backend `GET /api/games/{id}/reviews/summary`

## 4. 새 테이블을 채울 토픽 (JDBC Sink는 토픽 1개 → 테이블 1개)
지금 Connect로 채워지는 길이 있는 테이블은 `games`, `game_store_ids`, `prices_current`, `price_history`, `game_requirements`, `review_summaries` 6개뿐이다 (Kafka 토픽 10개 고정, 자동 생성 꺼짐). `erd.sql`의 나머지 테이블은 아직 채우는 경로가 없다.

| 테이블 | 제안 |
|---|---|
| `game_platforms`, `game_genres`, `game_companies`, `game_series_map`, `game_tags` | `refined.game_links`(또는 테이블별 토픽) + Connector |
| `platforms`, `genres`, `companies`, `game_series`, `tags` | 코드 테이블. 초기값은 SQL로 넣고, 새 값은 refiner가 함께 발행 |
| `game_aliases` | `refined.aliases` (IGDB 자동 + 검수한 LLM 표기, `reviewed`) |
| `game_time_to_beat`, `player_counts` | `topics.md`에 refined 토픽이 없음. 경로 결정 필요 |
| `exchange_rates` | 정제 담당이 출처 결정 후 적재 (날짜별 환율 권장, itad-notes 1절) |
| `user_owned_games` | Backend가 Steam 연동 시 직접 저장 (④) |

## 5. 그 밖에 확인할 것
- (해결) 커넥터 접속 주소 `mariadb-p` → `mariadb-pr`: Kafka 구축 문서 9장에 정리 작업(NW2-36)이 잡혀 있다.
- (해결) `collected_at`의 `Z` 문자열: Kafka 구축 문서 4장에 따라 refiner는 ISO 문자열 그대로 보내고, 변환은 Connect(TimestampConverter)가 한다.
- `refined.games` 한 메시지가 여러 행(장르·플랫폼·`game_store_ids`)이 되는 문제는 Kafka 문서 4장에도 미해결로 남아 있다. 토픽을 나눌지 정해야 하고, `refined.games` 메시지 예시를 contracts에 먼저 올려야 한다.
- `price_history`는 insert 모드라 같은 메시지가 두 번 오면 중복 행이 생긴다(at-least-once). UNIQUE를 걸면 Sink가 멈추므로, 중복은 refiner에서 막고 조회 시 `DISTINCT`로 보완하는 것을 제안한다.
- Primary `/DATA`가 4GB(binlog 3일치 포함)라 `price_history`가 가장 먼저 찰 수 있다. 용량 확인·확장 필요(MariaDB 문서 9장).
- ERD 적용 뒤에는 앱 계정의 CREATE·ALTER·DROP 권한이 회수되므로, 적용 전에 28개 구성을 확정해야 한다.
- 상품→게임 배정을 수집과 정제 중 어디서 할지 (column-mapping 12절 6번)

## 이미 erd.sql에 반영한 것 (계약 변경 없음)
- `price_history`에 메시지 필드 `price_original`, `currency_original`, `url` 추가 (없으면 Sink insert 실패)
- `games` 상세 컬럼(column-mapping 1절), `game_time_to_beat.ttb_count`
- `game_aliases`(출처 igdb | llm | manual, `reviewed`), `game_series`·`game_series_map`, `tags`·`game_tags`
- `stores.itad_shop_id`, `exchange_rates`, `user_owned_games`
- `game_store_ids` PK를 `(store, external_id)`로 (외부 번호 하나가 게임 둘에 붙지 않게)
- games의 쉼표 문자열(`genres`, `platforms`)을 연결 테이블로 정규화
