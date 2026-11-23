# ITAD 수집기

> 작성 2026-11-23 · 담당 한예찬 · 코드: `collector/collector/sources/itad.py`, 시험: `collector/tests/test_itad.py`
> API 세부는 `docs/collector-test/itad-notes.md`.

## 하는 일
`analysis/game_list/games_1000.csv`의 `itad_id`로 `POST /games/prices/v3?country=KR`을 불러 판매처별 현재가를 **원본 그대로** `raw.price`로 보낸다.

| 항목 | 값 |
|---|---|
| kind | `price` (계약 `docs/contracts/messages/raw.price.json`과 같은 모양) |
| 단위 | 게임 1건 = 봉투 1개. payload는 ITAD 응답 한 항목 `{id, historyLow, deals[]}` 그대로 |
| Kafka 키 | `itad_id` |
| 호출 | 100게임씩 한 번에 (`BATCH_SIZE`). 1,000게임 = 10회 |
| 통화 | 가격은 KRW로 온다. 환산은 필요 없다 |

- `request.params`에 `country`와 `steam_appid`를 넣는다. 정제기(`router.steam_hint`)가 게임 ID를 못 찾을 때 이 appid를 힌트로 쓴다. 키(`key`)는 봉투에 넣지 않는다.
- `itad_id`가 비어 있는 게임은 건너뛰고 경고 로그를 남긴다.
- ITAD가 돌려주지 않은 게임도 경고 로그로 남긴다.

## 제한과 안전
- 한도는 5분당 1,000건. 호출 간격 0.5초, 429·5xx는 `Retry-After` 또는 2·4·8초 간격으로 최대 3회 재시도.
- 키는 쿼리 파라미터로 가므로 예외 문구에는 경로와 상태 코드만 쓴다 (시험으로 확인).

## 실행
`.env`는 저장소 루트에 있으므로 **루트에서** 실행한다. 필요한 값: `ITAD_KEY`, `KAFKA_BOOTSTRAP`.
```bash
PYTHONPATH=collector python -m collector.main --source itad --dry-run --limit 5
PYTHONPATH=collector python -m collector.main --source itad
```
주기는 6시간이다. 스케줄(systemd 타이머)은 아직 없다 (IGDB와 같이 별도 작업).

## 시험 결과 (2026-11-23)
- 단위 테스트 8개 통과 (원본 유지·appid 힌트·키 미포함, 배치 분할, Retry-After, 재시도 포기, 오류에 키 없음, 호출 간격, 키 누락, CSV 읽기).
- `--dry-run --limit 5` 실제 호출 성공: 5/5건.
- 그 샘플을 정제기 `price.refine_price`에 넣어 보니 deal 전부가 `refined.prices` 행으로 바뀌고 unmatched는 0건이었다.

## 가격 이력 (`kind=price_history`, 2026-11-23 추가)
계약은 `docs/contracts/messages/raw.price_history.json` (PR #48로 `main`에 합쳐짐). 같은 토픽 `raw.price`로 보낸다.

| 항목 | 값 |
|---|---|
| 호출 | `GET /games/history/v2?id=<itad_id>&country=KR&since=<시각>` (게임당 1회) |
| 단위 | 게임 1건 = 봉투 1개. payload = `{"id": itad_id, "history": [응답 항목 그대로]}`, Kafka 키 `itad_id` |
| `request.params` | `id`, `appid`(문자열), `country`, `since`. 정제기가 게임을 찾는 힌트 |
| 최초 1회 | `--kind price_history` (전체 이력, `since=2000-01-01`). **`since`가 없으면 최근 약 3개월만 온다** |
| 주 1회 | `--kind price_history --since-days 14` (최근 14일치. 겹쳐도 정제·Backend가 합친다) |
| 크기 | 게임당 8~150KB(표본 7건, 최대 627건). 메시지가 800KB를 넘으면 `history`를 같은 모양으로 나눠 여러 개로 보낸다(Kafka 기본 한도 1MB 대비) |
| 소요 | 호출 간격 0.5초 → 1,000게임 약 8분 |

- 한 게임이 실패하거나 이력이 없으면 그 게임만 건너뛰고 계속한다 (건수는 마지막 로그에 남는다).
- **통화가 섞여 온다.** `itad-notes.md`는 "이력은 USD뿐"이라고 적었지만, 실제 응답은 한국에서 파는 판매처(Steam, Microsoft Store 등)는 KRW, 그 밖의 판매처는 USD(일부 GBP·EUR)로 왔다 (표본 3게임, 336건 중 KRW 203건). 환산은 정제기가 한다 (KRW는 그대로).
- 실행:
  ```bash
  PYTHONPATH=collector python -m collector.main --source itad --kind price_history --dry-run --limit 3
  PYTHONPATH=collector python -m collector.main --source itad --kind price_history --since-days 14
  ```
- 시험: 단위 테스트 8개 추가(총 67개). 실제 호출 `--limit 3`로 3/3건. 그 샘플을 **정제기(`main`, PR #49)의 `refine_price_history`**에 넣어 이력 항목 336개가 모두 `refined.price_history` 행이 되는 것을 확인했다 (매칭 실패 0건, 월평균 환율 적용).

## 아직 안 한 것
- Kafka 실제 전송 시험, 스케줄 (`igdb.md` 참고).
- 이 메시지를 받는 정제기(`refine_price_history`, 월평균 환율)는 PR #49로 `main`에 합쳐졌다.
