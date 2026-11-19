# pipeline — 정제 + Kafka Connect

**하는 일:** `raw.*` → 정제 → `refined.*`, 그리고 Kafka Connect로 DB 적재.
**배포:** Kafka 1~3 VM (refiner는 같은 consumer group으로 3대에서 실행)

## refiner 규칙
- consumer group: `refiner`. 처리 후 offset commit (at-least-once). 같은 메시지가 두 번 와도 결과가 같게(멱등) 만든다.
- 기준 게임 ID는 IGDB ID. 매칭 순서: ① IGDB external_games의 스토어 ID ② ITAD의 Steam appid ③ 다나와 상품명 정규화 후 이름 매칭.
- 매칭 실패한 데이터는 버리지 말고 `refined.unmatched`(로그용)로 보내고 개수를 로그에 남긴다.
- 원화 환산: ITAD가 KRW로 주면 그대로, 아니면 환율 적용. `price_original`, `currency_original`은 항상 채운다.
- refined.* 출력은 `docs/contracts/messages/refined.prices.json`의 **JSON+schema 형식** 그대로.
- 정제 로직은 Kafka 없이 테스트할 수 있게 순수 함수(`refiner/rules/`)로 분리하고 `tests/`에 샘플 기반 테스트를 둔다.

## connect 규칙
- 설정은 `connect/*.json`로만 관리하고 `connect/apply.sh`로 등록한다. 웹 UI에서 손으로 바꾸지 않는다.
- 비밀번호는 JSON에 쓰지 않는다 (`${file:...}` 또는 등록 시 환경 변수 치환).
- `prices_current`는 upsert(pk: game_id, store, edition), `price_history`는 insert.

## 재처리
정제 로직을 고친 뒤 처음부터 다시 처리할 때 (사용자 확인 후):
`kafka-consumer-groups.sh --bootstrap-server kafka1:9092 --group refiner --reset-offsets --to-earliest --all-topics --execute`
