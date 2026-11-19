# collector — 데이터 수집

**하는 일:** 외부에서 데이터를 받아 **원본 그대로** Kafka `raw.*` 토픽에 보낸다. 정제하지 않는다.
**배포:** Proxy·수집 서버 VM

## 출처별 규칙
| 출처 | 모듈 | 토픽 | 주기 | 제한 |
|---|---|---|---|---|
| ITAD | `sources/itad.py` | raw.price | 6시간 | 5분당 1000건 |
| IGDB | `sources/igdb.py` | raw.igdb | 매일 | 초당 4회 |
| Steam 리뷰·사용자 | `sources/steam.py` | raw.steam | 매일 / 요청 시 | – |
| 다나와 | `sources/danawa.py` | raw.console | 6시간 | 요청 사이 `DANAWA_REQUEST_DELAY_SEC` 이상 |

## 지킬 것
- 메시지는 `gamenuri_common.messages.RawEnvelope`로 만들고 `producer.publish()`로만 보낸다.
- 요청 제한을 코드로 강제한다 (sleep / 토큰 버킷). 429·5xx는 지수 백오프로 최대 3회 재시도.
- 다나와: robots.txt 확인 결과를 지키고, User-Agent에 프로젝트명을 넣는다. 페이지 구조가 바뀌면 파싱 실패를 로그로 남기고 멈추지 않는다.
- 개발 중에는 `--dry-run`으로 Kafka 대신 `samples/`에 JSON으로 저장할 수 있게 한다 (samples는 Git 제외).
- 수집 결과에서 필드를 빼거나 가공하지 않는다. 필요한 가공은 pipeline에 요청한다.

## 실행
```bash
pip install -e ../shared -r requirements.txt
python -m collector.main --source itad --dry-run
```
