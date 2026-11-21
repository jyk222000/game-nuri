# analysis — 분석

**하는 일:** Jupyter로 할인 주기 분석, 구매 타이밍 기준을 만들어 backend에 넘김, 발표용 차트.

## 지킬 것
- 데이터는 MariaDB **Replica**(`MARIADB_READ_HOST`)에서 읽기 전용 계정으로만 읽는다. 쓰지 않는다.
- 노트북 이름: `NN_주제.ipynb` (예: `01_할인주기.ipynb`). 커밋 전 출력은 지우거나 작게 유지.
- 데이터 파일(csv 등)은 `analysis/data/`에 두고 Git에 올리지 않는다.
- 구매 타이밍 기준이 정해지면 `docs/contracts/timing_rules.md`에 규칙으로 적고 backend에 알린다.

## 구조와 실행 (A: 노트북+이미지 / B: 서비스에 필요한 것만 JSON)
```
analysis/gamenuri_analysis/   계산(pandas)·그래프(matplotlib)·산출물. 노트북이 이걸 불러 쓴다
  mock_data.py                가설을 심은 가짜 데이터 (실데이터 전까지). loader.py 의 "db"는 정제 테이블 확정 후 구현
  a01~a08_*.py                분석 8개 (Notion '분석 방향'). run(data) → 그래프 PNG + summary.json
  export.py / run_all.py      B 산출물과 전체 실행
analysis/notebooks/           01~08 노트북 (출력 지운 채로 커밋)
analysis/out/                 생성물 (Git 제외)
```
```bash
pip install -e analysis -r analysis/requirements.txt
python -m gamenuri_analysis.run_all              # 계산 + out/figures/* (A) + out/api/*.json (B)
python -m gamenuri_analysis.run_all --publish    # + frontend/public/analysis-data, 프론트 목 API용 태그 복사
```
- **A** `out/figures/<분석>/summary.json` 안의 `charts`(차트용 숫자, `charts.py`) → 프론트 `/analysis`가 직접 그림(마우스 올리면 값).
  같은 변수로 `*.png`(matplotlib)도 만들어 화면의 "이미지(파이썬)" 버튼과 발표 자료에 쓴다. 계산은 파이썬만 하고 화면은 그리기만 한다.
  그래프를 추가할 때는 matplotlib 코드와 `res.attach_to("파일.png", ch.line(...))`를 같이 쓴다.
- **B** `out/api/game_insights.json`(게임별 분석 태그 → 게임 상세) · `spec_trust.json`(사양표 신뢰도 → 게임 상세 사양표 옆) · `timing_rules.json`(구매 타이밍 규칙 → Backend).
  Backend 인수 형식은 `docs/contracts/`에 올리기 전에 팀과 맞춘다 (위 규칙: timing_rules.md).
- 한글 폰트: Windows `Malgun Gothic`, Linux는 `NanumGothic` 설치 필요.
- mock 결과는 가설을 심은 가짜 값이다. 발표·문서에 결론처럼 쓰지 않는다.
