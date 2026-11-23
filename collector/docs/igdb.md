# IGDB 수집기

> 작성 2026-11-23 · 담당 한예찬 · 코드: `collector/collector/sources/igdb.py`, 시험: `collector/tests/test_igdb.py`

## 하는 일
`analysis/game_list/games_1000.csv`의 `game_id`(= IGDB ID) 1,000건을 IGDB에서 받아 **원본 그대로** `raw.igdb`로 보낸다.

| kind | 단위 | Kafka 키 | IGDB 엔드포인트 |
|---|---|---|---|
| `game_info` | 게임 1건 = 봉투 1개 | `igdb_id` | `/v4/games` |
| `time_to_beat` | 행 1건 = 봉투 1개 (payload에 `game_id`) | `game_id` | `/v4/game_time_to_beats` |

- 호출 수: 게임 정보 5회 + 클리어 시간 5회 (200건씩). 클리어 시간은 IGDB에 데이터가 있는 게임만 나온다.
- 요청 필드는 정제기(`pipeline/refiner/rules/game.py`, `links.py`)와 `docs/collector-test/column-mapping.md`가 쓰는 것을 모두 포함한다 (`GAME_FIELDS`). 하위 객체는 `genres.name`처럼 이름까지 펼쳐 요청한다.
- 응답은 가공하지 않는다. 일부 `game_localizations`에 `name`이 없는 것은 IGDB 원본이 그렇다 (정제기가 건너뛴다).

## 제한과 재시도
- 초당 4회 한도 → 호출 사이 0.26초 (`MIN_INTERVAL_SEC`).
- 429·5xx는 2·4·8초 간격으로 최대 3회 재시도. 401이면 Twitch 토큰을 한 번 다시 받는다.
- 오류 메시지에는 키를 넣지 않는다.
- IGDB가 돌려주지 않은 게임은 경고 로그로 남긴다.

## 실행
`.env`는 저장소 루트에 있으므로 **루트에서** 실행한다.
```bash
# 시험 (Kafka 없이 collector/samples/ 에 JSON 저장)
PYTHONPATH=collector python -m collector.main --source igdb --dry-run --limit 5
# 실제 전송
PYTHONPATH=collector python -m collector.main --source igdb
```
옵션: `--limit N` 앞에서 N개 게임만 · `--games-file` 게임 목록 CSV 지정.
필요한 `.env` 값: `TWITCH_CLIENT_ID`, `TWITCH_CLIENT_SECRET`, `KAFKA_BOOTSTRAP`.

## 시험 결과 (2026-11-23)
- 단위 테스트 8개 통과 (가짜 응답: 원본 유지, 배치 분할, 429 재시도, 재시도 포기, 401 토큰 재발급, 호출 간격, 키 누락, CSV 읽기).
- `--dry-run --limit 5` 실제 호출 성공: 게임 정보 5건, 클리어 시간 5건.
- 샘플 파일명은 `samples/raw.igdb.<kind>.<key>.json` (같은 키의 두 kind가 덮어쓰지 않게 `producer.py`에서 kind를 넣었다).

## 아직 안 한 것
- **Kafka 실제 전송 시험.** `--dry-run`만 확인했다.
- **실제 Kafka 서버 전송 시험.** 첫 실행은 `--limit 5`로 하고 `kafka-console-consumer`로 `raw.igdb`에 메시지가 쌓였는지 확인한다.

## 전송 실패 감지 (2026-11-23, 모든 수집기 공통, `collector/producer.py`)
- `produce()`의 전달 결과 콜백으로 성공·실패를 센다. 실패 상세(토픽, 이유)는 처음 5건만 로그로 남기고 메시지 내용은 남기지 않는다.
- 끝에서 `flush()`가 최대 60초 기다리고, 그때까지 못 보낸 메시지도 실패로 센다. 실패가 1건이라도 있으면 `collect FAILED` 오류 로그를 남기고 **종료 코드 1**로 끝난다 (systemd가 실패를 알 수 있다).
- Kafka에 닿지 않을 때 한 메시지는 60초 뒤 포기한다 (`message.timeout.ms`, 기본 5분).
- 대기열이 가득 차면 잠깐 비우고 최대 5번 다시 시도한다. 한 건의 로컬 오류(메시지가 너무 큼 등)로 전체를 멈추지 않는다.
- 같은 종류의 브로커 연결 오류는 한 번만 로그로 남긴다.
- 수집 도중 예외가 나도 이미 낸 메시지는 비우고, 원래 예외를 가리지 않는다.
- **Steam 리뷰의 "어디까지 받았나" 파일은 전송 성공을 확인한 뒤에만 저장한다.** 전송이 실패했는데 "받았다"고 기록하면 그 리뷰가 영영 빠지기 때문이다. 대신 수집 도중 오류로 끝나면 위치가 저장되지 않아 다음 실행에서 일부 리뷰를 다시 보낼 수 있다(중복 허용, 유실 방지).
- 시험: 가짜 Producer 단위 테스트 15개 + 아무도 듣지 않는 로컬 포트로 실제 클라이언트 실행(2건 모두 실패로 집계, 종료 코드 1). **실제 Kafka 서버에서는 아직 시험하지 못했다.**
- **매일 실행 스케줄** (systemd 타이머). 지금은 한 번 실행하고 끝난다.
- 전체 1,000건 실행.

## 배포
`proxy` VM(수집 서버)에서 실행한다 (`docs/network.md`). merge 후 `git pull` → venv → `pip install -e shared -r collector/requirements.txt` → `.env` 설정. 서버에서 명령을 실행하기 전에는 팀 규칙대로 확인을 받는다. `raw.igdb` 토픽은 `infra/kafka/`(남현식)에서 만들어져 있어야 한다.
