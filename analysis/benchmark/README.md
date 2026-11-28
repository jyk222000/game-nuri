# ES 벤치마크 2가지 (요구사항 #3 "왜 Elasticsearch인가")

| # | 비교 | 질문 | 상태 |
|---|---|---|---|
| ① | **게임 검색: MariaDB vs ES** | MariaDB `ILIKE`로 되는 검색에 ES를 더하면 무엇이 달라지나 (형태소·오타·띄어쓰기·잡음·응답 시간) | 계획만 있음, 아직 실행하지 않음 (아래 "① 게임 검색") |
| ② | **리뷰 키워드 추출: MongoDB vs ES** | 리뷰에서 게임별 핵심 키워드를 뽑는 일을 MongoDB 집계로 할 때와 ES(nori)로 할 때 무엇이 다른가 | 노트북 있음 (`09_벤치마크_ES_vs_MongoDB.ipynb`) |

게임 검색은 **MongoDB와 비교하지 않는다.** 현재 검색은 MariaDB(`backend/app/services/search.py`)이고 ES는 그 위에 더한 것(`SEARCH_BACKEND=es`)이기 때문이다.
키워드 추출은 MongoDB 집계(`$regexFindAll` → `$unwind` → `$group`)로 같은 일을 할 수 있어서 MongoDB와 비교한다.

## ② 리뷰 키워드 추출: MongoDB vs ES
이 프로젝트에서 ES를 쓰는 핵심 이유는 **리뷰 키워드 추출(⑤)** 이다. 그래서 같은 일을 MongoDB로 할 때와 비교한다.

| 방법 | 하는 일 | 형태소 분석 |
|---|---|---|
| ES | `review.nouns`(nori 명사)에 `terms` 집계 | 있음 (인덱스 안) |
| Mongo(집계) | `$regexFindAll` → `$unwind` → `$group`. 같은 불용어 적용 | 없음 |
| Mongo+Kiwi (선택) | 리뷰를 꺼내 Python 형태소 분석기로 명사 추출 | 있음 (DB 밖) |

세 방법 모두 "그 단어가 들어 있는 리뷰 수"로 순위를 매긴다(ES `terms` 집계와 같은 기준).

## 가설 (노트북 2장에서 데이터를 보기 전에 정한다)
| # | 가설 | 통계 도구 | 실무 기준 |
|---|---|---|---|
| H1 | ES가 조사·어미 붙은 가짜 키워드가 더 적다 (품질) | Wilcoxon 부호순위, 부트스트랩 | 20%p 이상 |
| H2 | ES가 더 빠르다 (속도) | Wilcoxon(로그 비율), 부트스트랩 | 1.5배 이상 |
| H3 | 리뷰가 많을수록 Mongo가 더 가파르게 느려진다 (규모) | 로그-로그 회귀, Spearman | 기울기 차이 0.2 이상 |
| H4 (탐색) | Mongo+Kiwi는 ES와 품질이 비슷하다 | Wilcoxon 양측, 동등 범위 ±10%p | – |

결과가 가설과 달라도 그대로 보고한다. 결론 문장은 계산 결과로 자동 생성된다.

## 실행
```bash
pip install -r analysis/requirements.txt
pip install kiwipiepy        # 선택 (Python 버전에 따라 설치가 안 될 수 있음)
```
접속 정보는 환경 변수로 넣는다(`shared/gamenuri_common/config.py`와 같은 이름). 코드·노트북에 쓰지 않는다.
```powershell
$env:MONGO_URI="mongodb://<계정>:<비밀번호>@<mongo 호스트>:27017/?authSource=admin"
$env:MONGO_DB="gamenuri_raw"
$env:ES_URL="http://<elk 호스트>:9200"
$env:ES_USER="elastic"       # ES_PASSWORD는 비워 두면 입력창이 뜬다
```
```bash
cd analysis/notebooks && jupyter lab     # 09_벤치마크_ES_vs_MongoDB.ipynb
```
노트북은 `analysis/notebooks/`에 있다(루트 `pyproject.toml`이 이 폴더를 ruff 검사에서 제외하므로). 이 폴더에서 열어야 결과 경로(`../results/benchmark`)가 맞는다.
* **읽기 전용**이다. 인덱스·데이터를 만들거나 지우지 않는다.
* **운영 DB에 질의를 보낸다.** 사용자가 적은 시간대에 실행하고, 느려지면 노트북 2장의 `N_GAMES`, `REPEATS`를 줄인다.
* Mongo `reviews`에 `payload.steam_appid` 인덱스가 없으면 노트북이 경고한다. 없으면 Mongo가 불리하게 측정되므로 결과에 "인덱스 없는 상태 기준"이라고 적는다.

## 결과
실행하면 `analysis/results/benchmark/`에 만들어진다(Git에 올릴지는 팀이 정한다).
`results.md`(요약 표), `summary.json`, `bench_per_game.csv`, 차트 PNG. 발표 자료와 `docs/tech-stack.md`에 쓸 때는 결과를 옮겨 적는다.

## ① 게임 검색: MariaDB vs ES (계획, 아직 실행하지 않음)
게임 검색을 ES에 연결했으므로(`SEARCH_BACKEND=es`, PR #182·#185) 이전 README의 부분·오타·정확도 비교를 **MongoDB가 아니라 MariaDB와** 비교하는 것으로 되살린다.

| 방법 | 내용 |
|---|---|
| MariaDB | `SEARCH_BACKEND=db`: 이름·한글명·별칭 `ILIKE %q%` + 띄어쓰기·기호 무시 비교 |
| ES | `SEARCH_BACKEND=es`: 위 결과 + ES(`games`·`game_aliases`) 결과를 합침(nori 형태소, 오타 허용 `AUTO:5,8`) |

**두 층으로 잰다.**
- **API 전체**: `GET /api/games?q=`를 스위치만 바꿔 호출(사용자가 느끼는 응답 시간·결과). 같은 서버를 `db`/`es`로 바꿔 재시작하거나 서버를 나눠서 잰다.
- **쿼리만**: MariaDB `SELECT`와 ES `_search`를 직접 호출(순수 검색 시간).

**검색어 세트** (정답 게임을 미리 정하고, 데이터를 보기 전에 확정한다)
| 종류 | 예 | 보는 것 |
|---|---|---|
| 정확·부분 | `엘든 링`, `엘든` | 정답을 찾는가 |
| 입력 중(접두) | `elden r` | 정답을 찾는가 |
| 한글 형태소 | `엘든링`, `엘든링을` | MariaDB 0건 → ES가 찾는가 |
| 영문 오타 | `elden rnig` | 정답 순위 |
| 띄어쓰기 다름 | `dead lock`↔`Deadlock`, `hollowknight`↔`Hollow Knight` (DB에 있는 게임으로 확정) | 양쪽 다 찾는가 |
| 잡음 | `cat` | 무관한 결과가 몇 개 나오는가 |
| 한계 | `아이작`(한글로 영문 게임) | 둘 다 못 찾는 것을 확인 (별칭 데이터 문제) |

**지표**: 정답 발견 여부, 정답 순위, 무관 결과 수(잡음), 응답 시간(같은 질의 100회 이상, 첫 호출 제외, 평균·p95).
**주의**: 게임이 1,000개 규모라 응답 시간 차이는 작을 수 있다. 그렇게 나와도 그대로 보고하고, 규모가 커질 때의 이야기는 따로 쓴다. 운영 DB·ES에 질의하므로 사용자가 적은 시간에 돌린다.

## 이전 계획과 달라진 점
처음 README는 "한글 부분 검색·오타·정확도"를 **MongoDB와 ES**로 비교하는 계획이었다. 검색은 MariaDB로 하고 있어서 비교 대상을 MariaDB로 바꾸고(① 위), MongoDB와의 비교는 **키워드 추출(②)**로 옮겼다.
`docs/requirements.md` #3, `docs/features.md`, `docs/decisions.md`(2026-11-28)에도 같은 내용으로 반영했다.
