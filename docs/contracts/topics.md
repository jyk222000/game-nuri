# Kafka 토픽

| 토픽 | 보내는 쪽 | 받는 쪽 | 키 | 파티션 | 복제 | 보관 |
|---|---|---|---|---|---|---|
| `raw.price` | collector (ITAD) | refiner, Mongo Sink | `itad_id` | 3 | 3 | 7일 |
| `raw.console` | collector (다나와) | refiner, Mongo Sink | `danawa_pcode` | 3 | 3 | 7일 |
| `raw.steam` | collector (Steam 리뷰(**1건 = 메시지 1개**)·리뷰 요약(GetItems)·사양(appdetails)·동접자·보유 게임) | refiner, Mongo Sink | `steam_appid` | 3 | 3 | 7일 |
| `raw.igdb` | collector (IGDB 게임 정보·클리어 시간) | refiner, Mongo Sink | `igdb_id` | 3 | 3 | 7일 |
| `refined.games` | refiner | JDBC Sink → `games` / Mongo Sink → `games` 컬렉션(→ Monstache → ES) | `game_id` | 3 | 3 | 3일 |
| `refined.prices` | refiner | JDBC Sink → `prices_current`(upsert) (이력은 `refined.price_history`로 따로 보낸다) | `game_id:store:edition:platform:item_condition` | 3 | 3 | 3일 |
| `refined.price_history` | refiner (ITAD history/v2 + 지금 가격이 바뀐 때만) | JDBC Sink → `price_history` (insert, 이 토픽만 읽음. 같은 줄이 여러 번 들어와도 Backend가 키 6개로 합친다) | `game_id:store:edition:platform:item_condition:collected_at` | 3 | 3 | 3일 |
| `refined.games_steam` | refiner (raw.steam app_details) | JDBC Sink → `games`의 `age_rating`·`korean_supported`·`is_online` (insert.mode=update, pk `game_id`) | `game_id` | 3 | 3 | 3일 |
| `refined.requirements` | refiner | JDBC Sink → `game_requirements` | `game_id` | 3 | 3 | 3일 |
| `refined.review_summary` | review-summarizer (하루 1회) | JDBC Sink → `review_summaries` | `game_id` | 3 | 3 | 3일 |
| `refined.genres` · `refined.companies` · `refined.tags` · `refined.game_series` | refiner (raw.igdb) | JDBC Sink → 같은 이름 테이블 (upsert) | 테이블 PK | 3 | 3 | 3일 |
| `refined.game_genres` · `refined.game_companies` · `refined.game_tags` · `refined.game_series_map` | refiner (raw.igdb) | JDBC Sink `jdbc-sink-game-links` → 같은 이름 테이블 (upsert) | 테이블 PK | 3 | 3 | 3일 |
| `refined.game_platforms` · `refined.game_aliases` · `refined.game_store_ids` | refiner (raw.igdb, 가격 매칭) | JDBC Sink → 같은 이름 테이블 (upsert) | 테이블 PK | 3 | 3 | 3일 |
| `refined.time_to_beat` | refiner (raw.igdb time_to_beat) | JDBC Sink → `game_time_to_beat` | `game_id` | 3 | 3 | 3일 |
| `refined.player_counts` | refiner (raw.steam player_count) | JDBC Sink → `player_counts` | `game_id:collected_at` | 3 | 3 | 3일 |
| `refined.exchange_rates` | refiner (가격 정제 환율) | JDBC Sink → `exchange_rates` | `rate_date:currency` | 3 | 3 | 3일 |
| `refined.unmatched` | refiner | (로그용, 매칭 실패 목록) | 원본 키 | 3 | 3 | 7일 |
| `clickstream` | backend | ES Sink (`clickstream-*` 인덱스), Backend 실시간 검색어 집계 | `session_id` | 3 | 3 | 3일 |

- 모든 메시지는 UTF-8 JSON.
- raw.* 메시지는 아래 **공통 봉투(envelope)** 안에 원본을 그대로 담는다.
- refined.* 메시지는 JDBC Sink가 읽을 수 있게 **JSON + schema** 형식으로 보낸다 (`messages/refined.prices.json` 참고).
- ITAD 가격 이력은 `raw.price`에 kind `price_history`로 보낸다 (`messages/raw.price_history.json`). 원화는 그 달 환율(월평균)로 정제에서 환산한다.
- 예시: `messages/` 폴더. 한 게임이 여러 행이 되는 토픽 14개는 `messages/refined.links.json` 한 파일에 모았다. Python 모델: `shared/gamenuri_common/messages.py`

## raw 공통 봉투
```json
{
  "schema_version": 1,
  "source": "itad | danawa | steam | igdb",
  "kind": "price | price_history | console_price | review | review_summary | owned_games | game_info | app_details | player_count | time_to_beat",
  "collected_at": "2026-11-19T02:30:00Z",
  "request": { "url": "...", "params": {} },
  "payload": { "...API 응답 원본 그대로..." }
}
```
