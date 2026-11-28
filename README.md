# 겜누리 (game-nuri)
게임 가격 비교 · 구매 타이밍 추천 서비스 — 더존 Python Pilot Project 2팀 · 발표 2026-11-30

PC 스토어(ITAD)·콘솔(다나와) 가격과 IGDB 게임 정보, Steam 사용자 데이터를 모아 **어디서, 언제 사는 게 가장 싼지** 알려 줍니다.

> **이 프로젝트의 주된 목적은 데이터 처리 과정(수집 → 전달 → 정제 → 저장 → 활용)을 배우는 것**입니다.
> 서비스 기능은 그 과정을 보여 주는 수단이고, 모든 기능은 "데이터가 어디서 와서 어디로 가는지" 설명할 수 있게 만들었습니다.

## 바로가기
| 보고 싶은 것 | 문서 |
|---|---|
| 팀 공통 지침 (사람·Claude 공통) | [`CLAUDE.md`](CLAUDE.md) |
| 기능·과제 명세 (기준 문서) | [`docs/features.md`](docs/features.md) |
| 필수 요구사항 체크리스트 | [`docs/requirements.md`](docs/requirements.md) |
| 구조·데이터 흐름 | [`docs/architecture.md`](docs/architecture.md), 구조도 [`docs/diagrams/`](docs/diagrams/) |
| 서버 이름·IP·포트 | [`docs/network.md`](docs/network.md) |
| 인프라 현황 | [`docs/infra-status.md`](docs/infra-status.md) |
| 기술 스택 (용도와 이득) | [`docs/tech-stack.md`](docs/tech-stack.md) |
| 결정 기록 | [`docs/decisions.md`](docs/decisions.md) |
| 팀 간 약속: API·토픽·메시지·테이블 | [`docs/contracts/`](docs/contracts/) ([`api.md`](docs/contracts/api.md), [`topics.md`](docs/contracts/topics.md), [`erd.sql`](docs/contracts/erd.sql)) |
| 전체 흐름 테스트 계획 | [`docs/test-plan.md`](docs/test-plan.md) |
| 서버 구축 워크북 (따라 하기) | [`infra/workbook/`](infra/workbook/README.md) (인프라·DB·Backend·백업), [`docs/workbook/이고은/`](docs/workbook/이고은/README.md) (ERD·정제) |
| 일정·이슈 | Jira `NW2` 프로젝트 |

## 서비스 기능 10개
| # | 기능 | 한 줄 설명 |
|---|---|---|
| ① | 가격 비교 | PC 스토어 8곳 + 다나와 콘솔 가격을 한 화면에서 비교 |
| ② | 구매 타이밍 · 할인 예측 | "지금 살지, 기다릴지" + 다음 할인 예상일·할인율 |
| ③ | 목표가 알림 · 메일 | 목표가에 도달하면 메일 발송 (Gmail SMTP) |
| ④ | 플레이 성향 맞춤 추천 | Steam 보유 게임·플레이타임 + 클리어 시간 기반 추천 |
| ⑤ | 리뷰 확인 · AI 요약 | ES로 키워드 추출 → **키워드만** AI에게 보내 한두 줄 요약 (하루 1회, 미리 계산) |
| ⑥ | PC 사양 추천 · 경고 | 게임 최소·권장 사양과 내 PC 사양을 AI가 비교 (결과 저장 후 재사용) |
| ⑦ | 동접자 기반 추천 · 경고 | 접속자 많은 게임 추천, 적은 온라인 게임 경고 |
| ⑧ | 구글 로그인 | 구글 계정으로 가입·로그인 (도메인 + HTTPS) |
| ⑨ | 실시간 검색어 | 검색 로그(클릭스트림) 기반 최근 1시간 TOP 10 |
| ⑩ | API 사용 순위 | Prometheus 계측 → 많이 쓰인 API 순위 |

**API는 47개**(메서드+경로 기준. 기능 단위로 묶으면 38개) — 번호와 형식은 [`api.md`](docs/contracts/api.md), 실제 동작은 Backend의 `/docs`(Swagger)에서 확인합니다.

## 데이터 흐름 (이 방향을 지킵니다)
```
수집기(collector) ──raw.*──▶ Kafka ──▶ 정제 프로그램(pipeline/refiner) ──refined.*──▶ Kafka
                                                                         │
            Kafka Connect(pipeline/connect) ◀────────────────────────────┘
              ├─ refined.*     → MariaDB        (정제값: 가격·게임·사용자·알림)
              ├─ raw.*         → MongoDB        (원본 JSON·리뷰)
              ├─ refined.games · game_aliases → MongoDB ──Monstache──▶ Elasticsearch (검색)
              ├─ raw.steam(리뷰) → MongoDB reviews ─Monstache─▶ Elasticsearch (키워드 추출)
              │      └─ (하루 1회) ES 키워드 → AI 요약 → refined.review_summary → MariaDB
              └─ clickstream   → Elasticsearch  (검색 로그·실시간 검색어·Kibana)
사용자 → Proxy(HAProxy) → Frontend 1·2 → Backend 1·2 → MariaDB / Elasticsearch / Valkey
                                          └─ clickstream ──▶ Kafka
```
- **수집기는 정제하지 않습니다.** 받은 원본을 그대로 `raw.*`에 보냅니다.
- **Backend는 DB에 가격·게임 데이터를 쓰지 않습니다.** 그 데이터는 Kafka Connect만 씁니다. Backend는 조회와 사용자·알림 데이터만 씁니다.
- **Frontend는 DB에 직접 붙지 않습니다.** 항상 자기 짝 Backend(`/api`)를 거칩니다 (FE1→BE1, FE2→BE2).

## 서버 구성
PC 2대 위에 VirtualBox VM 17대(Rocky Linux 10)를 두고, 컨테이너(Docker)는 쓰지 않습니다. 각 VM에서 venv + systemd 서비스로 실행합니다.

| PC | VM |
|---|---|
| PC-1 | proxy(HAProxy·수집기·NAT), frontend1·2, backend1·2, kafka1~3(브로커·정제·Connect), backup |
| PC-2 | monitoring(Prometheus·Grafana·NAT), mariadb-pr·re, mongodb-pr·mongo-se1·2, elk(Elasticsearch·Kibana·Monstache), valkey |

호스트 이름·IP는 [`docs/network.md`](docs/network.md)가 기준입니다. 코드에 IP·비밀번호·키를 쓰지 않고 `.env`(환경 변수)에서 읽습니다.

## 기술 스택
| 영역 | 선택 |
|---|---|
| 언어 | Python 3.12 (모든 Python 서비스), ruff(린트·포맷, 줄 길이 100), pytest |
| 수집 | requests, BeautifulSoup4(다나와), confluent-kafka |
| 정제 | confluent-kafka, pydantic v2 |
| 메시지·적재 | Kafka 3.8(KRaft, 브로커 3 + 투표 5), Kafka Connect, Monstache |
| 저장 | MariaDB 10.11(Primary→Replica), MongoDB 8.0(복제 셋 3대), Elasticsearch 8.19(nori), Valkey 8.1 |
| Backend | FastAPI, SQLAlchemy 2 + PyMySQL, redis-py, elasticsearch-py, Authlib(구글 로그인) |
| Frontend | React 18 + Vite 5, nginx가 빌드 결과를 서빙 |
| 운영 | HAProxy(HTTPS), Prometheus + Grafana, Locust(부하 테스트), Gmail SMTP, Gemini 등 AI API |

## 폴더
| 폴더 | 내용 | 담당 |
|---|---|---|
| [`collector/`](collector/) | ITAD·IGDB·Steam API 수집, 다나와 크롤링, Kafka Producer | 한예찬 |
| [`pipeline/`](pipeline/) | `refiner/` raw→refined 정제 · `connect/` Kafka Connect Sink 설정 | 이고은 · 남현식 |
| [`backend/`](backend/) | FastAPI API 서버 | 김준영 |
| [`frontend/`](frontend/) | 웹 화면 + nginx 설정 | 한예찬 |
| [`analysis/`](analysis/) | Jupyter 분석, 구매 타이밍 기준 | 전원 (분석별) |
| [`infra/`](infra/) | VM·네트워크·DB·모니터링·백업 설정과 스크립트, 구축 워크북 | 김준영 (kafka·elk·monitoring은 남현식) |
| [`shared/`](shared/) | 공통 Python 패키지 (설정, 메시지 모델, 로깅). **변경은 별도 PR·전원 리뷰** | 전원 |
| [`scripts/`](scripts/) | 데이터 흐름 검증, API 점검, 부하 테스트(Locust) | 김준영 |
| [`docs/`](docs/) | 설계 문서, 결정 기록, 팀 간 약속(`contracts/`, **변경은 별도 PR·전원 리뷰**) | 전원 |

## 시작하기 (로컬 개발)
각자 PC에서는 코드만 venv로 실행하고, Kafka·DB는 VM에 붙습니다. VM 없이 확인할 때는 mock 데이터와 pytest를 씁니다.
```bash
git clone <repo-url> && cd game-nuri
cp .env.example .env          # 값을 채운다. .env는 절대 커밋하지 않는다
python -m venv .venv && source .venv/bin/activate     # Windows(PowerShell): .venv\Scripts\Activate.ps1
pip install -e shared
pip install -r <내 파트>/requirements.txt             # 예: backend, collector, pipeline/refiner
pre-commit install            # 커밋 전에 ruff를 자동 실행
```
VM에 붙을 때는 `.env`의 호스트 이름만 VM 쪽으로 바꿉니다. 코드는 바꾸지 않습니다.

### 테스트와 검사
```bash
ruff check . && ruff format --check .       # 전체 린트·포맷 (CI와 같은 검사)
cd backend && pytest                        # 파트 폴더에서 실행: backend, collector, pipeline, shared, scripts
```
2026-11-28 기준 통과: backend 490 · collector 216 · pipeline 140 · scripts 7 · shared 6.

### Backend 실행
```bash
cd backend && uvicorn app.main:app --reload --port 8000
# 확인: http://localhost:8000/api/health , 명세: http://localhost:8000/docs
```
게임 검색은 환경 변수 `SEARCH_BACKEND`로 방식을 고릅니다: `db`(기본, MariaDB만) 또는 `es`(Elasticsearch를 더함, ES가 안 되면 자동으로 MariaDB로 대체).

## Git 규칙 (요약)
- `main`은 보호합니다. 직접 push하지 않고 PR + 1명 이상 리뷰 후 Squash merge합니다.
- 브랜치: `<파트>/<NW2-이슈번호>-<짧은설명>` (파트: infra, collector, pipeline, backend, frontend, analysis, docs, shared)
- 커밋: `[파트] 무엇을 했는지 (NW2-번호)`
- PR 하나에는 한 파트만 담고, `docs/contracts/`·`shared/` 변경은 따로 올립니다. PR 본문은 `.github/pull_request_template.md`를 따릅니다.
- 매일 작업 시작 전 `git pull --rebase origin main`.
- 자세한 규칙과 이름 규칙(시간 UTC, 금액 원화 정수, 기준 게임 ID = IGDB ID)은 [`CLAUDE.md`](CLAUDE.md)를 봅니다.
