# 분석 노트북

| 노트북 | 분석 | 담당 | 데이터 |
|---|---|---|---|
| `01_A1_할인패턴예측.ipynb` | A1 할인 패턴과 다음 할인 예측 (규칙성·시즌성·서비스 예측 규칙 정확도) | 한예찬 | MariaDB 추출 TSV 1개 (`a1_price_history.tsv`) |
| `05_A5_할인유형진정성.ipynb` | A5 "50% 할인"은 진짜 파격 세일인가 (할인 유형별 실질 구매가) | 한예찬 | A1과 같은 TSV + `games_1000.csv` |
| `02_A2_검색관심.ipynb` | A2 할인·출시와 국내 검색 관심 | 김준영 | MariaDB 추출 TSV 2개 + 네이버 검색어 트렌드(NAVER API HUB) |
| `08_A8_PC콘솔가격.ipynb` | A8 PC vs 콘솔 가격 차이 | 김준영 | MariaDB 추출 TSV 1개 |
| `03_A3_평론vs유저.ipynb` | A3 평론가 vs 유저 점수 차이, 한글화 수요 | 이고은 | `a3_games.tsv` |
| `04_A4_긍정불만유형.ipynb` | A4 긍정·불만 유형 (서버·버그·가격 불만과 긍정률) | 이고은 | `a4_keywords.tsv` + `games_1000.csv` |
| `09_벤치마크_ES_vs_MongoDB.ipynb` | 요구사항 #3 ES vs MongoDB 키워드 추출 비교 (별도 PR, 머지 후 이 폴더에 생김) | 김준영 | MongoDB·ES 직접 조회 (`../benchmark/README.md`) |

노트북은 **가설 → 데이터 처리 → 통계 검정 → 의미 판단 → 인사이트** 순서다.
소스 노트북은 출력을 지운 상태로 두고(`analysis/CLAUDE.md`), 실행 결과가 들어 있는 사본은 `executed/`에 둔다(GitHub 웹에서 바로 열람).

## 준비 (Windows PowerShell 기준)
```powershell
python -m pip install pandas numpy scipy seaborn statsmodels matplotlib requests jupyterlab
```
노트북은 `analysis\notebooks`에서 열어야 `../data` 경로가 맞는다. 다른 곳에서 열면 `GAMENURI_DATA_DIR`, `GAMENURI_RESULT_DIR` 환경 변수로 위치를 알려 준다.

## 1) 데이터 추출 (읽기만 한다)
`gamenuri_app` 계정은 `10.0.1.%`(Backend VM)에서만 접속되고 쓰기 권한도 있어 분석에 쓰지 않는다.
mariadb-re에서 `sudo mariadb`(root 소켓)로 **SELECT만** 실행한다. 실행 전에 쓰기 문장이 없는지 확인한다.
```bash
# PC: SQL을 VM으로
scp analysis\scripts\a2_games.sql analysis\scripts\a2_price_history.sql analysis\scripts\a8_extract.sql admina@mariadb-re:~/

# mariadb-re
grep -i -E "insert|update|delete|drop|alter|create|truncate|grant" ~/a2_*.sql ~/a8_extract.sql     # 출력이 없어야 함
sudo mariadb gamenuri -B --default-character-set=utf8mb4 < ~/a2_games.sql         > ~/a2_games.tsv
sudo mariadb gamenuri -B --default-character-set=utf8mb4 < ~/a2_price_history.sql > ~/a2_price_history.tsv
sudo mariadb gamenuri -B --default-character-set=utf8mb4 < ~/a8_extract.sql       > ~/a8_prices.tsv

# PC: 가져오기 (analysis\data 폴더는 Git이 무시한다)
mkdir analysis\data
scp admina@mariadb-re:~/a2_games.tsv admina@mariadb-re:~/a2_price_history.tsv admina@mariadb-re:~/a8_prices.tsv analysis\data\
```
`scp`가 여러 파일을 한 번에 못 받으면 한 줄에 하나씩 받는다.

A1·A5는 `analysis/scripts/a1_extract.sql` 하나를 같은 방식으로 실행해 `analysis/data/a1_price_history.tsv`로 저장한다(A1과 A5가 같은 파일을 쓴다).

## 2) A2만: 네이버 키
2026-07-31부터 신규 키는 **NAVER API HUB**(네이버 클라우드)에서만 발급된다. 개발자센터 키와 호출 주소·헤더가 달라 서로 호환되지 않는다.
Application을 등록할 때 **"검색어 트렌드" API를 함께 선택**해야 한다(없으면 401).
키는 코드·노트북에 쓰지 않고 아래 순서로 찾는다.
1. 환경 변수 `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET`
2. 저장소 루트 `.env`(Git이 무시) 두 줄: `NAVER_CLIENT_ID=...`, `NAVER_CLIENT_SECRET=...`
3. 없으면 호출 셀을 실행할 때 입력창이 한 번 뜬다.

개발자센터 키는 노트북 3-2의 `NAVER_PLATFORM = 'legacy'`로 바꾼다. 응답은 `analysis/data/naver_cache/`에 캐시되어 다시 실행해도 API를 부르지 않는다.
키를 PowerShell에 직접 입력하면 명령 기록에 남으니 `.env`나 입력창을 쓴다.

## 3) 실행
```powershell
cd analysis\notebooks
python -m jupyter notebook
```
`Kernel → Restart & Run All` 후 저장한다. 결과 PNG와 `summary.json`은 `analysis/results/a1`, `a2`, `a5`, `a8`에 생긴다.
실행 결과를 `executed/`에 올릴 때는 파일 크기가 1MB 아래인지, 출력에 키·내부 경로가 없는지 확인한다(`executed/README.md`).
