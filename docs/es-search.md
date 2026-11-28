# 게임 검색 Elasticsearch 연동 정리 (2026-11-27)

> 게임 검색(`GET /api/games?q=`)에 Elasticsearch(ES)를 붙인 작업의 요약과 기록이다.
> 실제 서버·코드로 확인한 것만 사실로 적었고, 확인하지 못한 것은 **미확인**으로 표시했다. 비밀번호·키는 적지 않았다.
> 담당: Backend 검색 서비스 김준영, ES 별칭 인덱스·Monstache·Kafka Connect 남현식.

## 1. 한 줄 요약
`SEARCH_BACKEND=es`로 켜면 ES(`games`·`game_aliases` 인덱스)가 찾은 게임을 MariaDB 부분 일치 결과에 **더해서** 보여 준다.
한글 형태소("엘든링을")와 영문 오타("elden rnig")까지 찾고, ES가 죽으면 MariaDB 검색으로 자동 대체한다. 기본값은 `db`(ES 미사용)다.

## 2. 왜 ES인가 (발표 예상 질문)
- 검색은 **MariaDB `ILIKE '%q%'`만으로도 되지만 형태소·오타 검색은 안 된다.** 예전 `search.py` 머리말에도 "ES 인덱스가 확정되면 연결한다"고 적혀 있었다.
- ES를 쓰는 **핵심 이유는 리뷰 키워드 추출(⑤)**이다(`review.nouns`에 nori 명사 집계). 게임 검색은 그 위에 얹은 보조 기능이다. 클릭스트림·Kibana도 같은 ES를 쓴다.
- 클릭스트림은 MongoDB로도 처리할 수 있다. "클릭스트림 때문에 ES가 꼭 필요하다"고는 말하지 않는다.
- **벤치마크는 2가지로 나눈다**(`docs/decisions.md` 2026-11-28): ① 게임 검색은 **MariaDB vs ES**(MongoDB와는 비교하지 않음, 아직 실행 안 함), ② 리뷰 키워드 추출은 **MongoDB vs ES**(노트북은 별도 브랜치 `analysis/NW2-xx-es-mongo-benchmark`, 계획과 방법은 `analysis/benchmark/README.md`).

## 3. 구조
```
[IGDB] → refiner → refined.games ────┬─ JDBC Sink → MariaDB games
                                     └─ Mongo Sink → MongoDB games ─ Monstache → ES games
                   refined.game_aliases ─┬─ JDBC Sink → MariaDB game_aliases
                                         └─ Mongo Sink → MongoDB game_aliases ─ Monstache → ES game_aliases (신규)

검색 q → Backend search.py
   ├─ MariaDB: 이름·한글명·별칭(source≠llm) 부분 일치 (띄어쓰기·기호 무시)  ← 항상 실행 (하한 보장)
   └─ ES (SEARCH_BACKEND=es): games + game_aliases 한 번에 검색 (형태소·오타)
        → 두 결과의 game_id를 합침 → 필터·정렬·카드는 기존 MariaDB 코드
   ES 장애·지연(2초) → 경고 로그 후 MariaDB 결과만
```
- Backend는 ES를 **읽기만** 한다. 색인은 Monstache만 한다(팀 규칙).
- 별칭을 ES `games`에 넣지 않은 이유: `refined.games`에는 별칭이 없고 `refined.game_aliases`는 MariaDB로만 갔다. `games`에 `aliases` 필드만 추가하면 비어 있게 되므로 **별칭 전용 인덱스**(문서 1개 = 별칭 1개)를 만들었다.

## 4. 작업 내용 (PR 순서)
| PR | 내용 | 담당 | 상태 |
|---|---|---|---|
| #182 `backend/NW2-xx-es-search-switch` | 검색 ES 스위치(`SEARCH_BACKEND`), ES 실패 시 MariaDB 대체, `source=llm` 별칭 검색 제외, 테스트 추가 | 김준영 | merge됨 |
| #183 `infra/NW2-xx-es-game-aliases` | `game_aliases` 인덱스 매핑, `mongo-sink-game-aliases`, Monstache 감시 추가와 `resume = false`, 서버 적용 | 남현식 | merge됨 |
| #185 `backend/NW2-xx-search-tuning` | 오타 허용을 긴 단어에만 적용(`AUTO:5,8`, `prefix_length 1`), 띄어쓰기·기호 무시 비교, 테스트 추가 | 김준영 | merge됨 |

### 4.1 Backend ([search.py](../backend/app/services/search.py), [config.py](../backend/app/core/config.py))
| 항목 | 내용 |
|---|---|
| 스위치 | `SEARCH_BACKEND` = `db`(기본) \| `es`. 인덱스 이름 `ES_GAMES_INDEX`(`games`), `ES_ALIASES_INDEX`(`game_aliases`). shared는 건드리지 않고 Backend 전용 설정에만 추가 |
| ES 쿼리 | `games,game_aliases`를 한 번의 호출로 검색. `name^2`·`name_ko^2`·`alias^2`에 오타 허용 `multi_match` + 입력 중 단어 접두 일치(`phrase_prefix`). `ignore_unavailable=True`라 별칭 인덱스가 없어도 오류 없음. 후보 500건 |
| 합치기 | ES가 준 `game_id`를 MariaDB 부분 일치와 **OR**로 합침 → `es`여도 결과가 `db`보다 줄지 않음. 정렬(`sort`)이 없으면 ES 점수 순이 먼저 |
| 대체 경로 | ES 연결 오류·시간 초과(요청 2초, 재시도 0)·이상한 응답이면 경고 로그만 남기고 MariaDB 결과로 처리. 500이 나지 않음 |
| AI 별칭 | `source='llm'` 별칭은 검수 여부와 상관없이 검색에서 뺌(MariaDB와 ES 쿼리 `must_not` 모두). 현재 DB에는 llm 별칭이 0건이라 실제 결과는 달라지지 않음 |
| 자동완성(#6) | ES를 쓰지 않음(입력마다 호출돼 지연 위험). 단, 띄어쓰기·기호 무시 비교는 적용됨 |
| 오타 허용 | `fuzziness: AUTO:5,8`, `prefix_length: 1`. 4글자 이하는 정확히 일치, 5~7글자 1글자, 8글자 이상 2글자 오타 허용 |
| 띄어쓰기 | 이름·한글명·별칭과 검색어에서 공백·탭·`- : ' ’ . , ! ? & ·`를 지우고 한 번 더 부분 일치. 기호뿐인 검색어는 아무것도 맞추지 않음 |

### 4.2 ES 별칭 인덱스 (남현식, #183)
- `infra/monstache/game-aliases-index.json`: nori `korean` 분석기, 필드 `game_id`(long), `alias`(text + `raw` keyword), `source`, `reviewed`, 복사본 0
- `pipeline/connect/mongo-sink-game-aliases.json`: `refined.game_aliases` → MongoDB `gamenuri_raw.game_aliases`, 키 `game_id`+`alias`
- `monstache.toml`: `game_aliases` 감시·매핑 추가, `resume = false`(오래 조용하다 재시작하면 `ChangeStreamHistoryLost`로 실시간 반영이 멈추던 문제. 대가는 재시작마다 reviews 45만 건 재복사, 수 분)

## 5. 확인한 사실 (2026-11-27)
| 확인 | 결과 | 방법 |
|---|---|---|
| ES `games` | 1000건, 문서에 `game_id`(숫자) 있음 | `_count`, `_search?size=1` |
| MariaDB `games` | 1000건 (ES와 일치) | `SELECT COUNT(*)` |
| MariaDB `game_aliases` | `igdb`·`reviewed=0`만 3,712건, **llm 0건** | `GROUP BY source, reviewed` |
| 별칭 건수 | MariaDB 3,712 / MongoDB 3,827 / ES 3,827 | 남현식 기록. 차이 115건은 MariaDB가 대소문자를 구분하지 않아 합치고 MongoDB는 따로 저장하는 규칙 차이(검색 결과는 같음) |
| 테스트 | backend 전체 490개 통과, ruff 통과 | 로컬 pytest (SQLite + 가짜 ES) |

### 5.1 검색 결과 비교 (backend1에서 실제 측정)
| 검색어 | `db`(이전) | `es` | 의미 |
|---|---|---|---|
| `엘든링` | 0건 | Elden Ring, Elden Ring Nightreign | 형태소 분석으로 "엘든 링"과 연결 |
| `엘든링을` | 0건 | Elden Ring | 조사가 붙어도 찾음 |
| `elden rnig` | 0건 | Elden Ring 1순위 + 잡음 3건(Elder Scrolls 등) | 오타 허용 (당시 설정 `AUTO`) |
| `elden r` | Elden Ring | Elden Ring | 접두 일치. 기존 결과 유지 |
| `인스크립션` | Inscryption | Inscryption | 기존 결과 유지 |

### 5.2 발견한 문제와 조치
| 문제 | 원인 | 조치 | 확인 |
|---|---|---|---|
| `cat` 검색에 VRChat 등 무관한 게임이 나옴 | `fuzziness: AUTO`가 3~5글자 단어에 1글자 오타를 허용해 `cat` → `chat`이 걸림 | `AUTO:5,8` + `prefix_length 1` (#185) | ES에 같은 쿼리를 직접 보내 `AUTO` 36건 vs `fuzziness 0` 0건(= 36건 전부 잡음)을 확인. **#185 배포 후 재확인은 미확인** |
| 띄어쓰기가 다르면 안 나옴(`dead lock` ↔ `Deadlock`, `hollowknight` ↔ `Hollow Knight`, `사이버 펑크`) | MariaDB는 글자 그대로 포함 여부만 봄, ES 영문은 단어 단위, nori 사전에 없는 합성어는 안 쪼개짐 | MariaDB 쪽에서 공백·기호를 뺀 비교를 추가(ES 인덱스 변경 없음) | 로컬 테스트로 확인. **실제 MariaDB에서는 미확인** |
| 한글로 검색하면 안 나옴(`아이작` 안 나오고 `isac`은 나옴) | 한글 이름·별칭이 데이터에 없음 | 코드로 해결 불가, 별칭 데이터 보충 필요(아래 7장) | 해당 게임의 `name_ko`·별칭 조회는 **미확인** |

## 6. 운영 방법
### 켜기 / 되돌리기 (backend1·backend2 **모두** 같게)
```bash
sudo -u backend -H git -C /opt/game-nuri/repo pull --rebase origin main     # 새 코드 반영
sudoedit /etc/game-nuri/backend.env      # 줄 추가: SEARCH_BACKEND=es (되돌릴 때는 db)
sudo systemctl restart backend && journalctl -u backend -n 30 --no-pager
curl -s http://localhost:8000/api/health   # es가 ok인지
```
- `ES_USER`·`ES_PASSWORD`가 `backend.env`에 있어야 한다. 비밀번호는 이 문서와 코드에 쓰지 않는다.
- 두 서버 설정이 다르면 HAProxy 라운드로빈 때문에 사용자마다 검색 결과가 달라진다.
- 배포 절차 기준: [infra/backend/README.md](../infra/backend/README.md).

### 확인 명령
```bash
for q in cat "dead lock" hollowknight "elden rnig" 엘든링; do
  echo "== $q"; curl -s -G http://localhost:8000/api/games --data-urlencode "q=$q" --data-urlencode "size=5" \
   | python3 -c 'import sys,json; [print(i["game_id"], i["name"], "/", i["name_en"]) for i in json.load(sys.stdin)["items"]]'
done
journalctl -u backend -n 50 --no-pager | grep -i "ES 실패" || echo "대체 경로 경고 없음"
```
"ES 실패, MariaDB로 대체"가 반복되면 ES 연결·계정 문제다(로그에 예외 이름이 찍힌다).

## 7. 한계와 남은 일
| 항목 | 내용 | 담당 |
|---|---|---|
| 한글↔영문 이름 연결 | `아이작` ↔ `Isaac`처럼 번역·음역은 별칭 데이터에 달려 있음. 발음 변환·임베딩은 이번 일정에 비현실적. 후보: 인기 게임에 `manual` 별칭 보충(DB 직접 입력은 팀 합의 후), Steam 한국어 이름·다나와 상품명 수집(파이프라인) | 김준영·이고은·한예찬 |
| 짧은 단어 오타 | 4글자 이하 오타는 교정되지 않음(`tera` → `terra`) | 수용 |
| 오타 검색 잡음 | 단어가 여러 개인 오타 검색은 관련 없는 결과가 뒤에 섞이고 `total`에 포함됨. 모든 단어 일치(AND)로 바꾸면 조사가 붙은 한글 검색이 실패해서 하지 않음 | 발표 후 검토 |
| 성능 | 공백·기호 제거 비교가 `REPLACE` 12번 중첩. 게임 1,000개 규모에서는 문제없을 것으로 보이나 실제 응답 시간은 **미측정** | 김준영 |
| ES 인덱스 개선 | 공백 제거 필드·n-gram은 재색인이 필요해서 하지 않음 | 남현식 |
| 계약·결정 문서 | `docs/contracts/topics.md`에 `refined.game_aliases` 새 소비자(Mongo Sink) 기록, `api.md` 5번의 "오타 허용은 ES 연동 후" 문구 갱신은 **아직 안 함**(contracts 별도 PR). `docs/decisions.md`에 "AI 별칭 검색 제외(근거: llm 0건)"도 **아직 없음** | 김준영 |
| 검색 벤치마크 ① | MariaDB vs ES(부분 일치·형태소·오타·띄어쓰기·잡음·응답 시간)는 **아직 안 함**. 계획은 `analysis/benchmark/README.md`. 키워드 추출 ②(MongoDB vs ES)는 노트북이 있고 실행 결과는 아직 없음 | 김준영 |
| 적용 범위 | backend1에서만 `es` 동작을 확인했다. backend2 적용·#185 배포 후 결과는 **미확인** | 김준영 |

## 8. 발표 말하기 포인트
- "ES를 쓴 핵심 이유는 한글 리뷰 키워드 추출이고, 게임 검색에도 같은 ES를 붙여 형태소·오타 검색을 더했다."
- "ES가 죽어도 검색은 된다. 스위치 하나로 켜고 끄고, ES 실패 시 MariaDB로 자동 대체한다."
- 시연 검색어: `엘든링`, `엘든링을`, `elden rnig`(Elden Ring이 1순위). 잡음이 섞일 수 있다는 점도 정직하게 말한다.
- 질문 대비
  - "검색은 MariaDB로도 되지 않나요?" → 부분 일치는 되지만 형태소("엘든링을")·오타("elden rnig")는 안 된다. 벤치마크 ①(MariaDB vs ES)로 답할 예정(아직 실행 전).
  - "키워드 추출은 MongoDB로도 되지 않나요?" → 집계로 할 수 있지만 형태소 분석이 없어서 "게임이/게임은"이 따로 세어지고, 형태소 분석을 하려면 DB 밖으로 꺼내 처리해야 한다. 벤치마크 ②(MongoDB vs ES) 노트북 참고.
  - "한글로 영문 게임이 안 나와요" → 별칭 데이터 문제이고 번역 검색은 향후 과제(Steam 한국어 이름·별칭 수집).
