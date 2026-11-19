# 겜누리 (game-nuri)
게임 가격 비교 · 구매 타이밍 추천 서비스 — 더존 Python Pilot Project 2팀

- 팀 공통 지침(사람·Claude 공통): [`CLAUDE.md`](CLAUDE.md)
- 구조: [`docs/architecture.md`](docs/architecture.md)
- 일정·이슈: Jira `NW2` 프로젝트

## 시작하기
```bash
git clone <repo-url> && cd game-nuri
cp .env.example .env          # 값 채우기 (커밋 금지)
python -m venv .venv && source .venv/bin/activate
pip install -e shared
pip install -r <내 파트>/requirements.txt
pre-commit install            # 커밋 전 ruff 자동 실행
```

## 폴더
| 폴더 | 내용 |
|---|---|
| `collector/` | 데이터 수집 (API·크롤링 → Kafka raw.*) |
| `pipeline/` | 정제(raw → refined) + Kafka Connect 설정 |
| `backend/` | FastAPI API |
| `frontend/` | 웹 화면 |
| `analysis/` | Jupyter 분석 |
| `infra/` | 서버 설정·스크립트 |
| `shared/` | 공통 Python 패키지 |
| `docs/` | 설계 문서, 팀 간 약속(contracts) |
