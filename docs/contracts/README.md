# 팀 간 약속 (contracts)

이 폴더는 **파트끼리 주고받는 형식**을 정의한다. 코드보다 여기가 먼저다.

| 파일 | 누가 쓰고 | 누가 읽나 |
|---|---|---|
| `topics.md`, `messages/*.json` | collector, refiner, backend(clickstream) | refiner, Kafka Connect |
| `erd.sql` | refiner(refined 형식), Kafka Connect | backend, analysis |
| `api.md` | backend | frontend |

## 바꾸는 방법
1. 이 폴더만 고친 PR을 따로 연다 (`docs/...` 브랜치).
2. PR 본문에 영향 받는 파트를 적고, 해당 담당자 전원의 승인을 받는다.
3. merge 후 각 파트가 자기 코드를 맞춘다.
4. 필드를 지울 때는 바로 지우지 말고 한 번은 `deprecated`로 표시한다.
