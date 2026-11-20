# ITAD API 수집 알아둘 점

`scripts/check_candidates.py`, `scripts/check_gaps.py`로 확인한 내용. 기준일: 2026-11-19. 키는 쿼리 파라미터(`key`)로 보내므로 예외 문구는 반드시 마스킹한다.

## 1. 통화: `games/history/v2`만 USD
| 엔드포인트 | 용도 | 통화 |
|---|---|---|
| `GET /games/prices/v3` (POST, `country=KR`) | 판매처별 현재가·정가·할인율, 전체/1년/3개월 최저가(`historyLow`) | KRW |
| `POST /games/overview/v2` | 현재 최저가·최저가·번들 | KRW |
| `POST /games/historylow/v1` | 역대 최저가와 일시 | KRW |
| `POST /games/storelow/v2` | 판매처별 최저가와 일시 (GET은 405) | KRW |
| `GET /deals/v2` | 할인 중 목록 | KRW |
| **`GET /games/history/v2`** | **가격 변동 이력(시계열)** | **USD만** |

- `history/v2`는 `country=KR`, `currency=KRW`, `since` 등을 줘도 가격이 `{"currency": "USD"}`로만 온다. `currency` 파라미터는 무시된다. `country=KR`은 통화가 아니라 **판매처 범위**를 한국에서 파는 곳으로 좁힌다(엘든 링 38건 → 8건).
- ITAD 사이트의 Country/Currency 옵션은 공개 API로는 확인되지 않았다(사이트 내부 환산으로 추정).
- **결정:** 수집 단계는 `history/v2` 원본을 USD 그대로 저장한다(원본 가공 금지 규칙). **원화 환산은 정제 단계에서 한다.** 현재가·최저가·deals는 KRW로 바로 받는다. 환율 출처(현재 환율 / 날짜별 환율)는 정제 담당이 정한다. 현재 환율로 과거 가격을 바꾸면 왜곡되므로, 이력 그래프의 원화 정확도가 중요하면 날짜별 환율이 필요하다.
- 금액 필드는 `amount`(소수, 원화는 정수값)와 `amountInt`(×100 단위 정수; USD는 센트)가 같이 온다.

## 2. 게임 ID 매핑 (Steam appid → ITAD id)
- `GET /games/lookup/v1?appid=<숫자>`. **`app/` 접두사를 붙이면 항상 `found:false`**이다. 접두사 형식(`app/1245620`)은 `POST /lookup/id/shop/{shopId}/v1`(Steam은 shopId 61)의 본문에서 쓴다.
- 처음 구현은 접두사를 붙여서 15개 전부 실패했고, 제목 조회 폴백으로 우연히 맞았다. 바이오하자드 4만 제목 `Resident Evil 4`가 appid 없는 다른 항목(`resident-evil-4`)에 붙어 가격·이력이 0건이었다. 올바른 항목은 `resident-evil-4-2023`.
- 현재 코드: ① appid 숫자 조회 → ② 실패하면 `games/search/v1` 결과 중 `games/info/v2`의 `appid`가 같은 항목 선택 → ③ 마지막으로 제목 조회(`_appid_verified`로 appid 일치 여부 표시, notes에 경고). 매칭 방법은 `lookup.json`의 `_match`에 남는다.
- 같은 appid가 에디션 항목에도 걸린다(`resident-evil-4-2023-gold-edition`도 2050650). appid 조회는 본편을 돌려줬지만, ITAD가 에디션을 별도 게임으로 둔다는 뜻이니 에디션 분류 때 참고한다.
- 검색(`games/search/v1`)은 DLC·코스튬까지 `type: dlc`로 섞여 온다. `type == "game"`만 본다.

## 3. 그 밖의 엔드포인트
- `GET /service/shops/v1?country=KR`: 판매처 35곳(`id`, `title`, `deals`, `games`, `update`). 명세의 "PC 스토어 8곳"은 이 목록에서 고른다.
- `GET /games/info/v2?id=`: `title`, `type`, `releaseDate`, `appid`, `tags`, `developers`, `publishers`, `reviews`(Steam·Metascore·Metacritic 유저·OpenCritic 점수와 건수), `players`(recent/day/week/peak), `stats`(rank, waitlisted, collected), `assets`(boxart·배너), `urls`.
- `prices/v3` 응답의 `deals[]`: `shop`, `price`, `regular`, `cut`, `voucher`, `storeLow`, `flag`, `drm`, `platforms`, `timestamp`, `expiry`, `url`.
- 한국 기준 판매처가 적다: 엘든 링은 현재가 판매처가 Steam과 GameBillet 2곳뿐.

## 4. 호출 한도
- 5분당 1,000건. 스크립트는 호출 간 0.3초 간격. 후보 15개 확인에 게임당 lookup 1 + history 1 정도라 여유가 크다.
