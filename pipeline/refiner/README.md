# refiner

`raw.*` 토픽을 읽어 정제한 뒤 `refined.*` 토픽으로 보낸다. 메시지의 `kind`로 규칙을 고른다.

| 들어오는 것 | 규칙 | 나가는 것 | 상태 |
|---|---|---|---|
| `raw.price` / `price` (ITAD 가격) | `rules/price.py` | `refined.prices` | 완료 |
| `raw.igdb` / `game_info` | `rules/game.py` | `refined.games` | 완료 (Steam 파생 컬럼은 비어 있음) |
| `raw.steam` / `app_details` | `rules/requirements.py` | `refined.requirements` | 완료 |
| `raw.console` / `console_price` (다나와) | `rules/console.py` | `refined.prices` | 신품만, 상품명 매칭은 정확 일치만 |
| 그 밖의 kind (review, player_count, time_to_beat 등) | 없음 | — | 건너뜀 |
| 매칭 실패·깨진 메시지 | — | `refined.unmatched` | 버리지 않고 기록 |

## 정제 규칙
- 빈 값은 NULL. 날짜는 `YYYY-MM-DD`, 시각은 수집 시각 UTC 문자열 그대로(DATETIME 변환은 Connect).
- 가격: KRW는 그대로, USD·EUR·GBP는 환율을 곱한다. `price_original`, `currency_original`은 항상 채운다.
  환율은 임시 고정값(USD 1400, EUR 1500, GBP 1800). 팀에서 정하면 바꾼다.
- 같은 (game_id, store, edition)은 낮은 가격 한 줄.
- 게임: 서비스 대상 플랫폼(PC, PS4, PS5, Switch, Switch2, XboxOne, XboxSeries)만 남기고 Mac 등은 뺀다.
- 사양: Steam HTML을 `OS: … / CPU: … / RAM: … / GPU: …` 텍스트로. 콘솔 전용 게임처럼 사양이 없으면 행을 만들지 않는다.
- 같은 메시지를 두 번 처리해도 결과가 같다 (입력만으로 결정).
- 출력은 `docs/contracts/messages/refined.*.json`과 같은 JSON+schema. 키는 `game_id:store:edition`(가격), `game_id`(게임·사양).

## 내 PC에서 시험 (Kafka 필요 없음)
```
cd pipeline
PYTHONPATH=.:../shared python -m refiner.main --dry-run --input raw.jsonl --id-map refiner/id_map.json --out out/
cd .. && python -m pytest pipeline/tests
```

## 서버(kafka1~3)에서 켜기 (남현식)
1. `cd /opt/game-nuri/repo && git pull`
2. `/etc/game-nuri/refiner.env`에 넣는다 (비밀번호 없음, Kafka는 인증 없음).
   ```
   KAFKA_BOOTSTRAP=kafka1:9092,kafka2:9092,kafka3:9092
   ID_MAP_PATH=/opt/game-nuri/repo/pipeline/refiner/id_map.json
   ```
3. `sudo systemctl start refiner` 후 `journalctl -u refiner -f`로 로그를 본다.
4. 같은 consumer group(`refiner`)이라 세 대가 파티션을 나눠 맡는다.

시험용 토픽으로 돌리려면 `REFINER_TOPICS_IN`, `REFINER_TOPIC_PRICES`, `REFINER_TOPIC_GAMES`,
`REFINER_TOPIC_REQUIREMENTS`, `REFINER_TOPIC_UNMATCHED`를 바꾼다.
실제 토픽에는 시험 메시지를 넣지 않는다 (넣은 메시지는 지울 수 없고 Connect가 DB에 넣는다).

## 아직 안 된 것 / 팀 결정이 필요한 것
- **Kafka 모드는 실제 Kafka에서 실행해 보지 못했다** (파일 시험만 통과). 처음 켤 때 로그를 같이 봐 주세요.
- `id_map.json`은 샘플 15개 게임용 임시 대응표 (`itad`: ITAD id, `steam`: Steam appid, `alias`: 정규화한 상품명).
  운영에서는 `game_store_ids`(또는 `refined.games`)로 대체해야 한다.
- **`refined.games`는 IGDB 한 메시지가 만드는 17개 컬럼 중 Steam 파생 3개(`age_rating`, `korean_supported`,
  `is_online`)가 비어 있다.** Steam 쪽 메시지와 합치는 방법(JDBC upsert는 안 쓴 컬럼을 덮어쓰지 않지만,
  `name`이 NOT NULL이라 Steam만 먼저 오면 실패한다)은 팀 결정이 필요하다.
- 한 메시지가 여러 행이 되는 것(장르·플랫폼·`game_store_ids`)은 `refined.games.extras`로만 만들고
  발행하지 않는다 (토픽 분리 결정 후).
- **다나와 가격**: 상품명을 정확히 맞출 때만 매칭한다(샘플에서는 대부분 unmatched). 같은 게임의 PS4·PS5가
  같은 키(`game_id, danawa, edition`)라 나중에 온 메시지가 덮어쓴다. `platform`·`item_condition`을 키에
  넣는 contracts 변경이 필요하고, 상품→게임 배정을 수집과 정제 중 어디서 할지도 정해야 한다.
- `price_history`는 재시작하면 같은 메시지가 두 번 들어갈 수 있다 (at-least-once). 중복 방지는 아직 없다.
