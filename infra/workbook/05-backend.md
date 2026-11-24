# 5. Backend (backend1, backend2)

FastAPI(Python)로 만든 API 서버입니다. 게임 검색·가격 비교·구매 타이밍·로그인·찜·목표가 알림·리뷰·사양 판정 API를 제공하고,
클릭스트림(검색·클릭 기록)을 Kafka로 보냅니다. 코드는 `backend/`, 실행 설정은 `infra/backend/`에 있습니다.
(구축 2026-11-23, 이후 기능 추가. `infra/backend/README.md`가 설치 기록 원본)

## 0. 만드는 것
```
frontend1 ──/api──▶ backend1 (FastAPI :8000, systemd 서비스 backend)
                      ├─ MariaDB Primary(쓰기·내 데이터) / Replica(조회)   ← 02-mariadb.md
                      ├─ Valkey(세션·캐시)                                  ← 03-valkey.md
                      ├─ Elasticsearch(검색·실시간 검색어, elk)
                      ├─ Kafka(clickstream 발행)
                      ├─ Steam API(GetOwnedGames), Google OAuth, Gemini(사양 판정)
                      └─ (주기 작업) 목표가 알림 메일 → Gmail SMTP
```
- 두 서버는 **같은 코드·같은 서비스 파일**이고, 환경 파일의 `SERVER_NAME` 만 다릅니다. frontend1→backend1, frontend2→backend2로 짝지어 연결됩니다.
- **현재는 backend1·frontend1만 운영**합니다. backend2·frontend2는 기능이 갖춰진 뒤 배포합니다(팀 합의).

Backend가 지키는 규칙 (`backend/CLAUDE.md`):
| 규칙 | 내용 |
|---|---|
| 쓰는 테이블 | `users`, `user_specs`, `notification_settings`, `user_owned_games`, `wishlists`, `alerts`, `alert_logs` **7개만**. 가격·게임 테이블은 Kafka Connect가 씀 |
| 읽기 | 조회는 Replica, **내 데이터는 Primary**. Replica 연결이 안 되면 Primary로 읽음 |
| AI 호출 | 사양 판정(⑥) 한 곳에서만, 결과는 Valkey에 저장해 재사용. 리뷰 요약(⑤)은 DB에서 **읽기만** |
| 비밀 | IP·비밀번호·키를 코드에 쓰지 않음. 모두 환경 파일에서 읽음 |

## 1. 준비물
| 항목 | 내용 |
|---|---|
| 먼저 끝나 있어야 할 것 | [01-공통준비](01-공통준비.md), [02-mariadb](02-mariadb.md)(계정·테이블), [03-valkey](03-valkey.md), ES(남현식, `http://elk:9200`), Kafka(남현식) |
| 레포·venv | `/opt/game-nuri/repo`, `/opt/game-nuri/repo/.venv` |
| 실행 계정 | `backend` (로그인 불가 시스템 계정) |
| 환경 파일 | `/etc/game-nuri/backend.env` (소유 root:backend, 권한 640) |
| 접속 | mariadb-pr·mariadb-re(3306), valkey(6379), elk(9200), kafka1~3(9092), 인터넷(443: Google, Steam, Gemini, Gmail SMTP 587) |

> <- DB 계정은 **가격·게임 테이블은 SELECT만** 줘야 안전합니다(앱 쓰기 가드는 직접 SQL을 막지 못함). 쓰기 권한은 위 7개 테이블만.

## 2. 설치 (backend1, backend2 각각 한 번)
```
# 대상 VM인지 확인
[admina@backend1 ~]$ hostname

# 파이썬 3.12 설치 확인 (Rocky 10 기본 저장소에 있음)
[admina@backend1 ~]$ python3.12 --version

# 레포 받기. /opt/game-nuri 에서 직접 clone 한다 (홈에서 mv 로 옮기면 SELinux 라벨 문제가 생김)
[admina@backend1 ~]$ cd /opt/game-nuri
[admina@backend1 game-nuri]$ git clone https://github.com/jyk222000/game-nuri.git repo
```
> <- 레포 접근에 인증이 필요하면 팀장에게 요청합니다(⚠ 미확인: VM에 저장된 인증 방식). 이후 `git pull` 은 아래 4장처럼 **`backend` 계정으로** 합니다.

```
# 가상환경 만들기 (이 앱 전용 파이썬 라이브러리 상자)
[admina@backend1 game-nuri]$ cd /opt/game-nuri/repo
[admina@backend1 repo]$ python3.12 -m venv .venv

# 공통 패키지(shared)와 Backend 라이브러리 설치
[admina@backend1 repo]$ .venv/bin/pip install -e shared -r backend/requirements.txt

# 실행 계정 만들기 (이미 있으면 건너뜀)
[admina@backend1 repo]$ sudo useradd --system --home-dir /opt/game-nuri --shell /sbin/nologin backend

# 레포를 옮겼거나 mv 했다면 SELinux 라벨을 복원한다 (안 하면 서비스가 203/EXEC Permission denied)
[admina@backend1 repo]$ sudo restorecon -Rv /opt/game-nuri
```
> <- `backend` 사용자가 `/opt/game-nuri/repo`(코드·venv)를 **읽을 수 있어야** 합니다.
> <- `requirements.txt` 가 `elasticsearch>=8.12,<9` 로 고정돼 있습니다. 서버가 ES 8.x인데 패키지가 9.x면 주소·계정이 맞아도 `es: down` 이 나옵니다(겪은 문제 참고).

## 3. 환경 파일 `/etc/game-nuri/backend.env`
이름과 설명은 `infra/backend/systemd/backend.env.example`에 있습니다. **값은 서버의 이 파일에만** 넣고 레포·채팅·명령줄에 쓰지 않습니다.
```
# 폴더 만들고 예시 파일을 복사 (소유 root:backend, 권한 640)
[admina@backend1 ~]$ sudo mkdir -p /etc/game-nuri
[admina@backend1 ~]$ sudo install -m 0640 -o root -g backend /opt/game-nuri/repo/infra/backend/systemd/backend.env.example /etc/game-nuri/backend.env

# 편집기로 값 채우기 (비밀번호·키는 여기서 직접 입력)
[admina@backend1 ~]$ sudoedit /etc/game-nuri/backend.env
```
| 변수 | 용도 | 비고 |
|---|---|---|
| `ENV`, `LOG_LEVEL` | 실행 환경, 로그 수준 | `vm`, `INFO` |
| `SERVER_NAME` | `/api/health`·클릭스트림에 찍히는 서버 이름 | backend1 서버는 `backend1`, backend2는 `backend2` |
| `MARIADB_HOST` / `MARIADB_READ_HOST` / `MARIADB_PORT` / `MARIADB_DB` | Primary·Replica 주소 | `mariadb-pr`, `mariadb-re`, `3306`, `gamenuri` |
| `MARIADB_USER` / `MARIADB_PASSWORD` | DB 계정 | 값은 서버에만 |
| `VALKEY_URL` | 세션·캐시 | `redis://:<비밀번호>@valkey:6379/0` |
| `KAFKA_BOOTSTRAP` | clickstream 발행 | `kafka1:9092,kafka2:9092,kafka3:9092` |
| `ES_URL` / `ES_USER` / `ES_PASSWORD` | Elasticsearch(검색) | `http://elk:9200`, 계정은 남현식에게 |
| `STEAM_KEY` | Steam 보유 게임 조회 | 키는 이 파일에만 |
| `PROMETHEUS_URL` | API 사용 순위(#37) | 비우면 순위가 `degraded` |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` / `GOOGLE_REDIRECT_URI` / `SESSION_SECRET` | 구글 로그인 | 아래 7장 |
| `GEMINI_API_KEY` / `AI_MODEL` | 사양 판정 AI | 아래 8장 |
| `SMTP_HOST` `SMTP_PORT` `SMTP_USER` `SMTP_PASSWORD` `MAIL_FROM` `PUBLIC_BASE_URL` | 목표가 알림 메일 | 아래 9장, **backend1만** |
| `AUTH_FAKE_USER` / `AUTH_FAKE_USER_ID` | 개발용 가짜 로그인 | **운영에서는 반드시 `false`** |

> <- **systemd 는 값 뒤의 `# 주석`을 값의 일부로 읽습니다.** 설명은 항상 **별도 줄**에 쓰고, 값 줄에는 값만 씁니다.
> <- 값에 공백·따옴표를 넣지 않습니다(Gmail 앱 비밀번호도 공백 없이 붙여서).

## 4. 서비스 등록·시작
```
# 서비스 파일 복사 (레포: infra/backend/systemd/backend.service)
[admina@backend1 ~]$ sudo cp /opt/game-nuri/repo/infra/backend/systemd/backend.service /etc/systemd/system/

# systemd 가 새 서비스 파일을 읽게 한다
[admina@backend1 ~]$ sudo systemctl daemon-reload

# 시작과 부팅 시 자동 시작
[admina@backend1 ~]$ sudo systemctl enable --now backend
```
서비스 파일 핵심:
```
> [Service]
> User=backend
> WorkingDirectory=/opt/game-nuri/repo/backend
> EnvironmentFile=/etc/game-nuri/backend.env
> ExecStart=/opt/game-nuri/repo/.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
> Restart=on-failure
> TimeoutStopSec=15
```
> <- 프로세스를 **1개**로 띄웁니다(`--workers` 없음). 워커가 여러 개면 `/metrics` 가 워커별로 갈라져 API 사용 순위(#37)가 틀어지기 때문입니다.
> <- `python -m uvicorn` 으로 실행하는 이유: venv의 `uvicorn` 스크립트를 직접 실행하면 SELinux 라벨 문제에 걸리기 쉽습니다.
> <- 종료 때 Kafka에 아직 안 나간 clickstream 메시지를 보내느라 최대 5초가 걸립니다.

## 5. 확인
```
# 서비스 상태 (active (running))
[admina@backend1 ~]$ systemctl status backend --no-pager

# 최근 로그
[admina@backend1 ~]$ journalctl -u backend -n 50 --no-pager

# 건강 상태
[admina@backend1 ~]$ curl -s http://localhost:8000/api/health
```
`/api/health` 해석:
| 항목 | 정상 | 의미 |
|---|---|---|
| `db_write` | `ok` | **ok 가 아니면 503**. Primary가 안 되면 서비스 불가 |
| `db_read` | `ok` | `down` 이어도 200 + `degraded`(앱이 Primary로 대신 읽음). Replica 접속(계정·`10.0.%` 허용)을 확인 |
| `valkey`, `es` | `ok` | 안 되면 200 + `degraded` |

```
# 다른 서버에서도 접속되는지 (backend2도 같은 방법)
[admina@frontend1 ~]$ curl -s http://backend1:8000/api/health

# 대표 API 확인 (장르 목록: {"items": [...]} 가 나온다)
[admina@backend1 ~]$ curl -s http://localhost:8000/api/genres | head -c 300
```

## 6. 코드를 업데이트할 때 (배포)
```
# git 은 backend 계정으로 실행한다. `sudo git ...`(root) 은 쓰지 않는다
[admina@backend1 ~]$ sudo -u backend -H git -C /opt/game-nuri/repo pull --rebase origin main

# 서비스 재시작 후 로그와 건강 상태 확인
[admina@backend1 ~]$ sudo systemctl restart backend && journalctl -u backend -n 30 --no-pager
[admina@backend1 ~]$ curl -s http://localhost:8000/api/health
```
> <- `sudo git pull` 을 쓰지 않는 이유: root로 실행하면 파일 소유자가 바뀌어 이후 `backend` 계정의 `git pull` 이 권한 오류로 막힐 수 있습니다.
> <- `backend/requirements.txt` 가 바뀐 배포일 때만 패키지를 다시 설치합니다: `sudo -u backend -H /opt/game-nuri/repo/.venv/bin/pip install -e shared -r backend/requirements.txt` (⚠ 미확인: 이 줄을 서버에서 실행해 본 기록 없음).
> <- **DB 칸을 추가하는 변경**(예: `variant_name`)은 DB에 칸을 먼저 추가한 **뒤에** 코드를 배포합니다.

## 7. 구글 로그인
`/api/auth/google/login` → 구글 → `/api/auth/google/callback` → 세션 쿠키 발급(Valkey `session:{id}`).
| 설정 | 내용 |
|---|---|
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | 구글 Cloud 콘솔의 OAuth 클라이언트 값 (한예찬 담당 콘솔) |
| `GOOGLE_REDIRECT_URI` | `https://gamenuri.store/api/auth/google/callback`. **콘솔에 등록한 값과 한 글자도 다르면 안 됨** |
| `SESSION_SECRET` | 로그인 state 쿠키 서명용 긴 임의 문자열. **backend1·backend2가 같은 값** |
| `AUTH_FAKE_USER` | 운영에서 반드시 `false` (true면 로그인 없이 가짜 사용자로 동작, 시작 로그에 경고) |

> <- 도메인(HTTPS)이 있어야 합니다: 구글 OAuth는 IP·HTTP redirect를 허용하지 않습니다(`docs/network.md`).
> <- 확인: 11/24에 `gamenuri.store` 에서 로그인이 끝까지 되는 것을 확인했습니다.

## 8. AI 사양 판정 (⑥)
`GET /api/games/{id}/spec-check` — 게임 사양과 내 PC 사양을 Gemini에 보내 `rec_ok / min_ok / below_min` 판정을 받고, **같은 조합이면 Valkey에서 재사용**(AI를 다시 부르지 않음).
| 설정 | 내용 |
|---|---|
| `GEMINI_API_KEY` | Gemini API 키 (서버 `backend.env`에만) |
| `AI_MODEL` | 사용할 모델 이름 |

> <- 둘 중 하나라도 비면 **503** 이 나가고 화면은 사양 표만 보여 줍니다(AI 없이 쓸 수 있는 대체 화면).
> <- Backend → Google(HTTPS 443)로 나가는 연결이 필요합니다. 사용자 식별 정보(이메일 등)는 AI에 보내지 않습니다.
> <- ⚠ 미확인: 서버에서의 실제 AI 호출은 프론트 작업 후 확인 예정입니다(400 `SPEC_REQUIRED` 경로까지만 확인).

## 9. 목표가 알림 메일 (NW2-74) — backend1에서만
가격이 목표가 이하가 된 알림에 메일을 보냅니다. API와 따로 도는 **주기 작업**(`backend-alerts.timer` → `python -m app.jobs.send_alerts`, 매시 50분)입니다.
- 규칙: 켜진 알림 + 메일 수신을 끄지 않은 사용자, 현재가(PC 우선 기준) ≤ 목표가. **같은 가격에는 다시 보내지 않고, 더 내려가면 다시** 보냅니다. 보낸 뒤에도 알림은 켜 둡니다.
- backend1에서만 켭니다(backend2도 켜면 같은 메일이 두 번 나갈 수 있음).

**준비**
1. 발신용 구글 계정에서 **2단계 인증**을 켜고 **앱 비밀번호**를 발급합니다(공백 없이 붙여서 사용).
2. `backend.env` 에 `SMTP_USER`(**전체 메일 주소**, 앱 이름이 아님), `SMTP_PASSWORD`, `PUBLIC_BASE_URL` 을 넣습니다.
3. 서버에서 Gmail SMTP로 나가는지 확인합니다.
```
# 587 포트가 열려 있는지 (open 이 나와야 함)
[admina@backend1 ~]$ timeout 5 bash -c '</dev/tcp/smtp.gmail.com/587' && echo open || echo blocked
```

**확인 순서**
```
# 1) 예시 메일 한 통을 내 주소로만 보낸다 (DB 안 씀, 실제 사용자에게 안 감)
[admina@backend1 ~]$ cd /opt/game-nuri/repo/backend
[admina@backend1 backend]$ sudo -u backend -H bash -c 'set -a; . /etc/game-nuri/backend.env; set +a; /opt/game-nuri/repo/.venv/bin/python -m app.jobs.send_alerts --test-to <내 메일 주소>'
> 예시 메일 1통 발송 완료 → j***@gmail.com

# 2) 보낼 대상만 출력 (보내지 않음). 메일 주소는 가려서 나온다
[admina@backend1 backend]$ sudo -u backend -H bash -c 'set -a; . /etc/game-nuri/backend.env; set +a; /opt/game-nuri/repo/.venv/bin/python -m app.jobs.send_alerts --dry-run'
```
> <- 받은편지함(스팸함 포함)에서 1)을 확인하고 2)의 대상이 맞으면 3)으로 갑니다. **3)의 첫 실행은 대상이 있으면 진짜 메일이 나갑니다.**

```
# 3) 서비스와 타이머 등록
[admina@backend1 ~]$ sudo cp /opt/game-nuri/repo/infra/backend/systemd/backend-alerts.service /opt/game-nuri/repo/infra/backend/systemd/backend-alerts.timer /etc/systemd/system/
[admina@backend1 ~]$ sudo systemctl daemon-reload

# 한 번 실제로 실행하고 로그 확인
[admina@backend1 ~]$ sudo systemctl start backend-alerts.service
[admina@backend1 ~]$ journalctl -u backend-alerts -n 20 --no-pager
> 알림 메일: 대상 1건, 발송 1건, 건너뜀 0건, 실패 0건

# 같은 명령을 한 번 더: 대상 0건이어야 한다 (같은 가격은 다시 안 보냄)
[admina@backend1 ~]$ sudo systemctl start backend-alerts.service && journalctl -u backend-alerts -n 5 --no-pager

# 주기 실행 시작과 다음 실행 시각 확인
[admina@backend1 ~]$ sudo systemctl enable --now backend-alerts.timer
[admina@backend1 ~]$ systemctl list-timers 'backend-alerts*' --no-pager
```
> <- 종료 코드: 0 정상, 1 일부 발송 실패(다음 실행에서 재시도), 2 설정 오류(비어 있는 환경 변수 이름이 로그에 나옴).
> <- 한 번에 보내는 메일은 최대 200통(설정 실수 방지).
> <- 한계: 가격이 목표가 위로 올랐다가 **같은 가격으로** 다시 내려오면 새 알림으로 보지 않습니다(더 내려가면 보냄).
> <- 11/25 backend1에서 위 순서로 확인했습니다(첫 실행 발송 1건, 두 번째 대상 0건).

## 10. 코드 구조 (유지보수하는 사람용)
```
backend/app/
  main.py         FastAPI 앱, 라우터 등록, /api/health
  api/            라우터 (얇게 유지: games, auth, me, search, reviews, events ...)
  services/       비즈니스 로직 (timing, prices, cards, taste, spec_check, alert_mail ...)
  jobs/           주기 작업 (send_alerts)
  db/             SQLAlchemy 모델·세션 (erd.sql 과 일치, 읽기 전용 테이블 쓰기 가드)
  clients/        es, valkey, kafka, steam, prometheus 접속
  core/           설정(config.py), 오류 형식, Valkey 키 규칙(keys.py)
backend/tests/    pytest (SQLite 메모리 DB, 외부 서비스는 가짜)
```
```
# 로컬에서 테스트·검사 (VM 없이)
[내 PC backend]$ python -m pytest -q
[내 PC backend]$ python -m ruff check app tests && python -m ruff format --check app tests
```
> <- API 경로·응답 형식의 기준은 `docs/contracts/api.md` 입니다. 바꿔야 하면 contracts PR을 먼저 올립니다.

## 11. 겪은 문제
| 문제 | 원인 | 해결 |
|---|---|---|
| `status=203/EXEC` `Permission denied` | 레포를 홈에서 `mv` 로 옮겨 SELinux 라벨이 `user_home_t` | `sudo systemctl stop backend && sudo restorecon -Rv /opt/game-nuri && sudo systemctl start backend`. 예방: `/opt/game-nuri` 에서 직접 clone, SELinux는 끄지 않음 |
| `/api/health` 의 `es: down` (계정은 맞음) | 파이썬 `elasticsearch` 패키지 9.x와 서버 8.19 불일치 | `requirements.txt` 를 `<9` 로 고정(PR #88), backend1은 `pip` 으로 직접 맞춤. 확인: `.venv/bin/pip show elasticsearch` |
| 환경 파일의 값에 이상한 글자가 붙음 | systemd 가 값 뒤 `# 주석`을 값으로 읽음 | 설명을 별도 줄로 분리(`backend.env.example` 수정) |
| 로컬 `.env` 의 `MARIADB_HOST` 가 "label too long" | 원인 미확인(줄을 고쳐서 해결) | 값 줄만 남기고 다시 작성 |
| `sudo git pull` 후 권한 오류 | root 로 실행해 소유자가 바뀜 | 항상 `sudo -u backend -H git -C ...` |
| 알림 메일 `SMTPServerDisconnected` (로그인 단계) | `SMTP_USER` 에 메일 주소가 아니라 **앱 이름**을 넣음 | 전체 메일 주소로 수정 (비밀번호 값은 길이·형식만 확인하고 출력하지 않음) |

## 12. 남은 일
- [ ] 알림 메일 로그인 실패 시 오류 출력 정리(지금은 Traceback)
- [ ] backend2 배포 (기능이 갖춰진 뒤)
- [ ] 검색을 ES로 전환(MariaDB 대체 유지), 실시간 검색어 저장소 확정(ES vs Valkey sorted set)
- [ ] AI 사양 판정의 서버 실제 호출 확인
