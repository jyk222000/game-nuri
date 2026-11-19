# 겜누리(game-nuri) — 팀 공통 지침

> 이 파일은 팀원 4명의 Claude Code가 **모두 똑같이 읽는** 기준 문서입니다.
> 여기 적힌 규칙이 각자 PC에서 작업할 때의 기본값입니다. 바꾸려면 PR로 바꾸고 팀 전원이 확인합니다.

## 1. 프로젝트 한 줄 요약
서비스명 **겜누리 (game-nuri)**.

> **이 프로젝트의 주된 목적은 데이터 처리 과정(수집 → 전달 → 정제 → 저장 → 활용)을 배우는 것**이다.
> 서비스 기능은 그 과정을 보여 주는 수단이다. 기능을 만들 때도 "데이터가 어디서 와서 어디로 가는지"가
> 설명 가능하게 만든다. 필수 요구사항 목록은 `docs/requirements.md` (전부 구현 대상).
>
> **확정 범위: 서비스 기능 10개 · API 38개 · 기술·발표 과제 8개** → `docs/features.md`가 기준.
게임 가격 비교 · 구매 타이밍 추천 서비스. PC 스토어(ITAD)·콘솔(다나와) 가격과 IGDB 게임 정보,
Steam 사용자 데이터를 모아 **어디서, 언제 사는 게 가장 싼지** 알려준다. 발표 11/30.

## 2. 데이터 흐름 (반드시 이 방향을 지킨다)
```
수집기(collector) ──raw.*──▶ Kafka ──▶ 정제 프로그램(pipeline/refiner) ──refined.*──▶ Kafka
                                                                         │
            Kafka Connect(pipeline/connect) ◀────────────────────────────┘
              ├─ refined.*     → MariaDB   (정제값: 가격·게임·사용자·알림)
              ├─ raw.*         → MongoDB   (원본 JSON·리뷰)
              ├─ refined.games → MongoDB games ──Monstache──▶ Elasticsearch games (검색)
              ├─ raw.steam(리뷰) → MongoDB reviews ─Monstache─▶ Elasticsearch reviews (키워드 추출)
              │      └─ (하루 1회) ES 키워드 → AI 요약 → refined.review_summary → MariaDB
              └─ clickstream   → Elasticsearch (검색 로그·실시간 검색어·Kibana)
사용자 → Proxy(HAProxy) → Frontend 1·2 → Backend 1·2 → MariaDB / Elasticsearch / Valkey
                                          └─ clickstream ──▶ Kafka
```
- **수집기는 정제하지 않는다.** 받은 원본을 그대로 `raw.*`에 보낸다.
- **Backend는 DB에 가격 데이터를 쓰지 않는다.** 가격·게임 데이터는 Kafka Connect만 쓴다. Backend는 조회 + 사용자/알림 데이터만 쓴다.
- **Frontend는 DB에 직접 붙지 않는다.** 항상 자기 짝 Backend(`/api`)를 거친다 (FE1→BE1, FE2→BE2).

## 3. 디렉터리와 담당
| 폴더 | 내용 | 배포 VM | 담당 |
|---|---|---|---|
| `collector/` | ITAD·IGDB·Steam API 수집, 다나와 크롤링, Kafka Producer | Proxy·수집 서버 | (미정) |
| `pipeline/refiner/` | raw → refined 정제 (중복 제거, 원화 환산, 게임 ID 통합) | Kafka 1~3 | (미정) |
| `pipeline/connect/` | Kafka Connect Sink 설정 JSON | Kafka 1~3 | (미정) |
| `backend/` | FastAPI API 서버 | Backend 1·2 | (미정) |
| `frontend/` | 웹 화면 + nginx 설정 | Frontend 1·2 | (미정) |
| `analysis/` | Jupyter 분석, 구매 타이밍 기준 | 각자 PC | (미정) |
| `infra/` | VM·네트워크·DB·모니터링·백업 설정과 스크립트 | 각 VM | (미정) |
| `shared/` | 공통 Python 패키지 (메시지 모델, 설정, 로깅) | 모든 Python 서비스 | **전원 (PR 필수 리뷰)** |
| `docs/contracts/` | 토픽·메시지 형식, ERD, API 명세 = **팀 간 약속** | – | **전원 (PR 필수 리뷰)** |

### 현재 담당 (11/20~ 전체 흐름 테스트 기준, 본 개발 분담 확정 시 갱신)
| 사람 | 역할 | 주로 만지는 폴더 |
|---|---|---|
| 남현식 | Kafka 전담 (클러스터, 연결, Kafka Connect) | `infra/kafka/`, `pipeline/connect/` |
| 한예찬 | 수집 (원본 수집, 프로파일링, Producer) | `collector/` |
| 이고은 | DB 설계 · 정제 (정규화·ERD, 정제 로직) | `docs/contracts/erd.sql`, `pipeline/refiner/` |
| 김준영 (팀장) | 인프라 · 검증 (VM·DB 설치, 직접 적재, 전체 검증) | `infra/`, `scripts/` |

테스트 계획: `docs/test-plan.md`. `.github/CODEOWNERS`의 `@TBD`는 GitHub 아이디로 채운다.

## 4. Claude가 작업할 때 지킬 규칙
1. **자기 파트 폴더만 수정한다.** 다른 파트 폴더를 고쳐야 하면 수정하지 말고, 무엇을 왜 바꿔야 하는지 사용자에게 알린다.
2. **`docs/contracts/`와 `shared/`는 약속이다.** 바꿀 때는 ① 사용자에게 먼저 알리고 ② 이 둘만 담은 별도 PR로 올리고 ③ 영향을 받는 파트를 PR 본문에 적는다. 몰래 필드 이름을 바꾸지 않는다.
3. **메시지·테이블·API를 새로 만들 때는 먼저 `docs/contracts/`를 읽고 그 형식을 따른다.** 형식이 없으면 contracts에 먼저 추가한 뒤 코드를 쓴다.
4. **IP·포트·비밀번호·API 키를 코드에 직접 쓰지 않는다.** 모두 환경 변수(`.env`)에서 읽는다. 호스트는 IP 대신 호스트 이름(`kafka1`, `mariadb-p` 등, `docs/network.md`)을 쓴다.
5. **`.env`, 키 파일은 읽거나 출력하거나 커밋하지 않는다.** 새 설정값이 필요하면 `.env.example`에 이름과 설명만 추가한다.
6. **VM(서버)에서 명령을 실행하기 전에 사용자에게 확인한다.** 특히 DB 삭제·초기화(`DROP`, `TRUNCATE`, `rm -rf`, `dropDatabase`, 토픽 삭제, `docker volume rm`)는 절대 스스로 실행하지 않는다.
7. **작은 단위로 커밋한다.** 커밋 메시지는 아래 Git 규칙을 따른다.
8. 막히거나 계약과 실제가 다르면 추측해서 고치지 말고 사용자에게 보고한다.
9. **AI API는 사용자 요청마다 부르지 않는다.** 배치로 미리 만들거나(⑤), 처음 한 번 부르고 결과를 저장해 재사용한다(⑥). 리뷰 원문을 AI에게 보내지 않는다(키워드만). 응답은 JSON 형식으로 받고, 실패하면 AI 없이 보여 줄 대체 화면을 둔다.

## 5. 기술 스택 (고정)
| 영역 | 선택 |
|---|---|
| 언어 | Python 3.11 (모든 Python 서비스 공통) |
| 패키지 | 서비스별 `requirements.txt` + `pip install -e ../shared` |
| 코드 스타일 | ruff (lint + format), 줄 길이 100, 타입 힌트 필수 |
| 수집 | requests, BeautifulSoup4 (다나와), confluent-kafka |
| 정제 | confluent-kafka, pydantic v2 |
| Backend | FastAPI + SQLAlchemy 2 + PyMySQL, redis-py(Valkey), elasticsearch-py |
| Frontend | **팀 확정 필요** (권장: React + Vite → 빌드 결과를 nginx가 서빙) |
| 테스트 | pytest |
| 로그인 | 구글 OAuth (Authlib) — 도메인(DDNS) + HTTPS 필요 |
| 동기화 | Monstache (MongoDB → Elasticsearch) |
| API 모니터링 | prometheus-fastapi-instrumentator → Prometheus → Grafana |
| 부하 테스트 | Locust |
| 메일 | Gmail SMTP (앱 비밀번호) |
| AI | Gemini 등 AI API — ⑤ 리뷰 요약(ES 키워드만 전송), ⑥ 사양 비교. 결과는 저장해 재사용 |
| 실행 방식 | **컨테이너 사용 안 함.** 각 VM에서 venv + systemd 서비스로 실행 |
| OS | Ubuntu Server 24.04 LTS |

## 6. 이름 규칙
- 서비스명 표기: 화면·문서·발표는 **겜누리**, 레포·폴더·서버 경로·도메인은 **`game-nuri`**,
  Python 패키지·DB·컬렉션처럼 하이픈을 못 쓰는 곳은 **`gamenuri`** (예: `gamenuri_common`, DB `gamenuri`).
- Python: 파일·함수·변수 `snake_case`, 클래스 `PascalCase`, 상수 `UPPER_SNAKE`.
- Kafka 토픽: `raw.<출처>`, `refined.<대상>`, `clickstream` (점으로 구분, 소문자).
- DB 테이블·컬럼: `snake_case`, 테이블은 복수형 (`games`, `price_history`).
- API 경로: `/api/<복수명사>` (예: `/api/games/{game_id}/prices`). JSON 키는 `snake_case`.
- 시간은 **항상 UTC, ISO 8601** (`2026-11-19T02:30:00Z`)로 저장·전송하고, 화면에서만 KST로 바꾼다.
- 금액은 **원화 정수**(`price_krw`)로 저장한다. 원래 통화는 `price_original`, `currency_original`에 따로 둔다.
- **기준 게임 ID = IGDB ID** (`game_id`). 스토어별 ID는 `game_store_ids` 테이블에서 연결한다.

## 7. Git 규칙
- `main`은 보호한다. 직접 push 금지, PR + 1명 이상 리뷰 후 merge.
- 브랜치: `<파트>/<NW2-이슈번호>-<짧은설명>` 예) `collector/NW2-27-danawa-crawler`
  - 파트: `infra`, `collector`, `pipeline`, `backend`, `frontend`, `analysis`, `docs`, `shared`
- 커밋: `[파트] 무엇을 했는지 (NW2-번호)` 예) `[collector] 다나와 검색 결과 파싱 추가 (NW2-27)`
- PR 하나에는 한 파트만. contracts/shared 변경은 따로 PR.
- merge 방식: Squash merge.
- 매일 작업 시작 전 `git pull --rebase origin main`.

## 8. 환경 변수
`.env.example`을 복사해서 각자 `.env`를 만든다. **`.env`는 절대 커밋하지 않는다.**
서비스는 `shared/gamenuri_common/config.py`의 `Settings`로만 환경 변수를 읽는다.

## 9. 로컬 개발
VM 없이 각자 PC에서 개발할 때는 `infra/local/docker-compose.yml`로 Kafka·MariaDB·Valkey를 띄운다.
```bash
docker compose -f infra/local/docker-compose.yml up -d
python -m venv .venv && source .venv/bin/activate
pip install -e shared -r <내 파트>/requirements.txt
```
VM에 붙을 때는 `.env`의 호스트 이름만 VM 쪽으로 바꾼다. 코드는 바꾸지 않는다.

## 10. 자주 쓰는 문서
- 전체 구조: `docs/architecture.md`
- IP·포트·호스트 이름: `docs/network.md`
- 토픽·메시지 형식: `docs/contracts/topics.md`, `docs/contracts/messages/`
- DB 테이블: `docs/contracts/erd.sql`
- API 명세: `docs/contracts/api.md`
- **최종 기능 명세 (기준 문서): `docs/features.md`**
- 필수 요구사항 체크리스트: `docs/requirements.md`
- 전체 흐름 테스트 계획: `docs/test-plan.md`
- 결정 기록: `docs/decisions.md` (중요한 결정은 날짜와 이유를 한 줄로 남긴다)
