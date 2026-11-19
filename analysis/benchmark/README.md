# ES vs MongoDB 검색 벤치마크 (요구사항 #3)

같은 게임 데이터(MongoDB `games` ↔ ES `games`, Monstache로 동기화된 같은 내용)로 비교한다.

| 비교 항목 | MongoDB 방법 | ES 방법 | 측정 |
|---|---|---|---|
| 한글 부분 검색 ("엘든") | `$regex` / `$text` | `match` (nori) | 결과 정확도, 응답 시간 |
| 오타 검색 ("엘든릉") | 불가 또는 regex | `fuzziness: AUTO` | 찾았는지 여부 |
| 정확도 정렬 | 불가 (text score 제한) | relevance score | 상위 5개 품질 |
| 응답 시간 | 같은 쿼리 1,000회 | 같은 쿼리 1,000회 | 평균, p95 |

결과는 `results.md`에 표로 정리하고, 차트는 `docs/tech-stack.md`와 발표 자료에 넣는다.
