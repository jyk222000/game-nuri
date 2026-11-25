# ES vs MongoDB 벤치마크 (요구사항 #3 "왜 Elasticsearch인가")

## 무엇을 비교하나
이 프로젝트에서 ES를 쓰는 이유는 **리뷰 키워드 추출(⑤)** 이다. 그래서 같은 일을 MongoDB로 할 때와 비교한다.
게임 검색은 현재 MariaDB로 하므로(`backend/app/services/search.py`) ES 도입 이유로 쓰지 않는다.

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

## 이전 계획과 달라진 점
이전 README는 "한글 부분 검색·오타·정확도" 검색 비교였다. 검색은 아직 ES에 연결하지 않았으므로 **키워드 추출 비교로 바꿨다.**
`docs/requirements.md` #3, `docs/features.md`의 문구는 별도 docs PR로 맞춘다.
(나중에 게임 검색을 ES에 연결하면 부분·오타·정확도 비교를 같은 방식으로 추가할 수 있다.)
