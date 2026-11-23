# refiner

`raw.*` 토픽을 읽어 정제한 뒤 `refined.*` 토픽으로 보낸다. 메시지의 `kind`로 규칙을 고른다.

| 들어오는 것 | 규칙 | 나가는 것 | 상태 |
|---|---|---|---|
| `raw.price` / `price` (ITAD 가격) | `rules/price.py` | `refined.prices` | 완료 |
| `raw.igdb` / `game_info` | `rules/game.py` | `refined.games` | 완료 (Steam 파생 컬럼은 비어 있음) |
| `raw.steam` / `app_details` | `rules/requirements.py` | `refined.requirements` | 완료 |
| `raw.console` / `console_price` (다나와) | `rules/console.py` | `refined.prices` | 플랫폼·신품/중고 구분, 상품명 매칭은 정확 일치만 |
| 그 밖의 kind (review, player_count, time_to_beat 등) | 없음 | — | 건너뜀 |
| 매칭 실패·깨진 메시지 | — | `refined.unmatched` | 버리지 않고 기록 |

## 정제 규칙
- 빈 값은 NULL. 날짜는 `YYYY-MM-DD`, 시각은 수집 시각 UTC 문자열 그대로(DATETIME 변환은 Connect).
- 가격: KRW는 그대로, USD·EUR·GBP는 환율을 곱한다. `price_original`, `currency_original`은 항상 채운다.
  환율은 임시 고정값(USD 1400, EUR 1500, GBP 1800). 팀에서 정하면 바꾼다.
- 같은 (game_id, store, edition, platform, item_condition)은 낮은 가격 한 줄. ITAD는 `PC`·`new`.
- 게임: 서비스 대상 플랫폼(PC, PS4, PS5, Switch, Switch2, XboxOne, XboxSeries)만 남기고 Mac 등은 뺀다.
- 사양: Steam HTML을 `OS: … / CPU: … / RAM: … / GPU: …` 텍스트로. 콘솔 전용 게임처럼 사양이 없으면 행을 만들지 않는다.
- 같은 메시지를 두 번 처리해도 결과가 같다 (입력만으로 결정).
- 출력은 `docs/contracts/messages/refined.*.json`과 같은 JSON+schema. 키는 `game_id:store:edition:platform:item_condition`(가격), `game_id`(게임·사양).

## 내 PC에서 시험 (Kafka 필요 없음)
```
cd pipeline
PYTHONPATH=.:../shared python -m refiner.main --dry-run --input raw.jsonl --id-map refiner/id_map.json --out out/
cd .. && python -m pytest pipeline/tests
```

## 한 게임이 여러 행이 되는 토픽 14개 (`rules/links.py`)
`raw.igdb` 게임 정보 하나에서 장르·회사·태그·시리즈·플랫폼별 출시일·별칭·스토어 번호를 각각의 토픽으로 보낸다.
형식은 `docs/contracts/messages/refined.links.json` (필드 = erd.sql 컬럼).

| 토픽 | 테이블 | 출처 |
|---|---|---|
| `refined.genres`, `refined.game_genres` | `genres`, `game_genres` | IGDB genres |
| `refined.companies`, `refined.game_companies` | `companies`, `game_companies` | IGDB involved_companies (개발·배급) |
| `refined.tags`, `refined.game_tags` | `tags`, `game_tags` | IGDB themes, keywords (keyword tag_id = 10,000,000 + id) |
| `refined.game_series`, `refined.game_series_map` | `game_series`, `game_series_map` | IGDB collections, franchises (수집 필드에 있어야 함) |
| `refined.game_platforms` | `game_platforms` | IGDB platforms + release_dates |
| `refined.game_aliases` | `game_aliases` | 이름, 한글 이름, alternative_names |
| `refined.game_store_ids` | `game_store_ids` | Steam appid, 처음 연결된 ITAD id, 매칭된 다나와 pcode |
| `refined.time_to_beat` | `game_time_to_beat` | `raw.igdb` kind `time_to_beat` |
| `refined.player_counts` | `player_counts` | `raw.steam` kind `player_count` (appid는 `request.params.appid`) |
| `refined.exchange_rates` | `exchange_rates` | 가격 정제에 쓴 환율, 하루 1번 |

## 서버(kafka1~3)에서 켜기 (남현식)
1. `cd /opt/game-nuri/repo && git pull`
2. `/etc/game-nuri/refiner.env`에 넣는다 (비밀번호 없음, Kafka는 인증 없음).
   ```
   KAFKA_BOOTSTRAP=kafka1:9092,kafka2:9092,kafka3:9092
   ID_MAP_PATH=/opt/game-nuri/repo/pipeline/refiner/id_map.json
   ID_MAP_STATE_PATH=/var/lib/game-nuri/refiner_id_map.json
   ```
3. `sudo systemctl start refiner` 후 `journalctl -u refiner -f`로 로그를 본다.
4. 같은 consumer group(`refiner`)이라 세 대가 파티션을 나눠 맡는다.

시험용 토픽으로 돌리려면 `REFINER_TOPICS_IN`, `REFINER_TOPIC_PRICES`, `REFINER_TOPIC_GAMES`,
`REFINER_TOPIC_REQUIREMENTS`, `REFINER_TOPIC_UNMATCHED`를 바꾼다.
실제 토픽에는 시험 메시지를 넣지 않는다 (넣은 메시지는 지울 수 없고 Connect가 DB에 넣는다).

## 아직 안 된 것 / 팀 결정이 필요한 것
- **Kafka 모드는 실제 Kafka에서 실행해 보지 못했다** (파일 시험만 통과). 처음 켤 때 로그를 같이 봐 주세요.
- **게임 ID 대응표** (`itad`: ITAD id, `steam`: Steam appid, `alias`: 정규화한 상품명 → IGDB ID)
  1. 시작 대응표 `ID_MAP_PATH`: 게임 목록 CSV로 만든다.
     `python -m refiner.build_id_map --csv games.csv --out refiner/id_map.json --base refiner/id_map.json`
     (열: `igdb_id, steam_appid, itad_id, name, name_ko, aliases`)
  2. 스스로 배우기: `raw.igdb`를 받으면 Steam appid·게임 이름을 배우고, `raw.price`에 Steam appid 힌트
     (`payload.steam_appid` 또는 `request.params.appid`)가 있으면 ITAD id도 배운다.
     배운 것은 `ID_MAP_STATE_PATH`에 저장해 재시작해도 남는다.
  3. **주의:** 배우기는 서버마다 따로다. refiner 3대가 파티션을 나눠 받으면, 게임 정보를 받은 서버와
     가격을 받은 서버가 다를 수 있다. 그래서 **1번 시작 대응표를 주로 쓰고**, 테스트는 kafka1 한 대로
     켜거나 수집 순서를 IGDB → Steam → ITAD → 다나와로 한다. 운영에서는 `game_store_ids`로 대체한다.
- **`refined.games`는 IGDB 한 메시지가 만드는 17개 컬럼 중 Steam 파생 3개(`age_rating`, `korean_supported`,
  `is_online`)가 비어 있다.** Steam 쪽 메시지와 합치는 방법(JDBC upsert는 안 쓴 컬럼을 덮어쓰지 않지만,
  `name`이 NOT NULL이라 Steam만 먼저 오면 실패한다)은 팀 결정이 필요하다.
- 한 메시지가 여러 행이 되는 것(장르·플랫폼·`game_store_ids`)은 `refined.games.extras`로만 만들고
  발행하지 않는다 (토픽 분리 결정 후).
- **다나와 가격**: 상품명을 정확히 맞출 때만 매칭한다(샘플에서는 대부분 unmatched). 플랫폼은
  `platform_hint`, 없으면 상품명에서 찾고 못 찾으면 unmatched. 상품→게임 배정 방법은 정해야 한다.
- `games.aggregated_rating`·`aggregated_rating_count`는 IGDB 응답에 있으면 채운다(수집 필드 추가 필요).
  플랫폼별 출시일(`game_platforms.release_date`)은 `extras.platform_release_dates`로만 만든다.
- `price_history`는 재시작하면 같은 메시지가 두 번 들어갈 수 있다 (at-least-once). 중복 방지는 아직 없다.
