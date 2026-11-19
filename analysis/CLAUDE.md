# analysis — 분석

**하는 일:** Jupyter로 할인 주기 분석, 구매 타이밍 기준을 만들어 backend에 넘김, 발표용 차트.

## 지킬 것
- 데이터는 MariaDB **Replica**(`MARIADB_READ_HOST`)에서 읽기 전용 계정으로만 읽는다. 쓰지 않는다.
- 노트북 이름: `NN_주제.ipynb` (예: `01_할인주기.ipynb`). 커밋 전 출력은 지우거나 작게 유지.
- 데이터 파일(csv 등)은 `analysis/data/`에 두고 Git에 올리지 않는다.
- 구매 타이밍 기준이 정해지면 `docs/contracts/timing_rules.md`에 규칙으로 적고 backend에 알린다.
