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

## 아직 안 한 것
- **가격 이력(`games/history/v2`, USD).** 정제기에 이 데이터를 받는 `kind`가 없고, `shared/messages.py`의 `Kind`에도 없다. 만들려면 `shared/`·`docs/contracts/`를 바꾸는 별도 PR과 팀 합의가 필요하다. 분석(A1)이 이력을 쓰는 방식과 ②의 이력 그래프를 어떻게 채울지(우리가 쌓는 스냅샷 vs ITAD 이력)를 먼저 정해야 한다.
- Kafka 실제 전송 시험, 전송 실패 감지, 스케줄 (IGDB와 같다. `igdb.md` 참고).
