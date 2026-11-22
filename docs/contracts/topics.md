# Kafka 토픽

| 토픽 | 보내는 쪽 | 받는 쪽 | 키 | 파티션 | 복제 | 보관 |
|---|---|---|---|---|---|---|
| `raw.price` | collector (ITAD) | refiner, Mongo Sink | `itad_id` | 3 | 3 | 7일 |
| `raw.console` | collector (다나와) | refiner, Mongo Sink | `danawa_pcode` | 3 | 3 | 7일 |
| `raw.steam` | collector (Steam 리뷰·사양(appdetails)·동접자·보유 게임) | refiner, Mongo Sink | `steam_appid` | 3 | 3 | 7일 |
| `raw.igdb` | collector (IGDB 게임 정보·클리어 시간) | refiner, Mongo Sink | `igdb_id` | 3 | 3 | 7일 |
| `refined.games` | refiner | JDBC Sink → `games`, `game_store_ids` / Mongo Sink → `games` 컬렉션(→ Monstache → ES) | `game_id` | 3 | 3 | 3일 |
| `refined.prices` | refiner | JDBC Sink → `prices_current`(upsert), `price_history`(insert) | `game_id:store:edition:platform:item_condition` | 3 | 3 | 3일 |
| `refined.requirements` | refiner | JDBC Sink → `game_requirements` | `game_id` | 3 | 3 | 3일 |
| `refined.review_summary` | review-summarizer (하루 1회) | JDBC Sink → `review_summaries` | `game_id` | 3 | 3 | 3일 |
| `refined.unmatched` | refiner | (로그용, 매칭 실패 목록) | 원본 키 | 3 | 3 | 7일 |
| `clickstream` | backend | ES Sink (`clickstream-*` 인덱스), Backend 실시간 검색어 집계 | `session_id` | 3 | 3 | 3일 |

- 모든 메시지는 UTF-8 JSON.
- raw.* 메시지는 아래 **공통 봉투(envelope)** 안에 원본을 그대로 담는다.
- refined.* 메시지는 JDBC Sink가 읽을 수 있게 **JSON + schema** 형식으로 보낸다 (`messages/refined.prices.json` 참고).
- 예시: `messages/` 폴더. Python 모델: `shared/gamenuri_common/messages.py`

## raw 공통 봉투
```json
{
  "schema_version": 1,
  "source": "itad | danawa | steam | igdb",
  "kind": "price | console_price | review | owned_games | game_info | app_details | player_count | time_to_beat",
  "collected_at": "2026-11-19T02:30:00Z",
  "request": { "url": "...", "params": {} },
  "payload": { "...API 응답 원본 그대로..." }
}
```
