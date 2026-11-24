# Backend 실행 (backend1·backend2)

FastAPI 코드는 `backend/`, 실행 설정만 여기 둔다. VM에서 하는 작업은 사용자가 직접 실행한다(설치 전 스냅샷).
두 서버는 같은 코드·같은 유닛이고 `.env`의 `SERVER_NAME`만 다르다. Frontend 1→Backend 1, Frontend 2→Backend 2로 이어진다(`frontend/nginx/`).

## 준비물
| 항목 | 내용 |
|---|---|
| 레포·venv | `/opt/game-nuri/repo`, `/opt/game-nuri/repo/.venv` (`pip install -e shared -r backend/requirements.txt`) |
| DB 계정 | MariaDB 서비스 계정(`docs/infra-status.md`의 `gamenuri_app`). **가격·게임 테이블은 SELECT만** 주는 것이 진짜 방어선이다(앱의 쓰기 가드는 직접 SQL을 막지 못한다). 쓰기 권한은 `users`·`user_specs`·`notification_settings`·`user_owned_games`·`wishlists`·`alerts`·`alert_logs` 7개 테이블만. |
| 접속 | mariadb-pr·mariadb-re(3306), valkey(6379, 비밀번호), kafka1~3(9092) |

## 설치 (backend1, backend2 각각 한 번)
```bash
# 0) 스냅샷. 레포 최신화 + venv (git은 sudo 없이 backend 계정으로. 아래 '코드를 업데이트할 때' 참고)
cd /opt/game-nuri/repo
python3.12 -m venv .venv && .venv/bin/pip install -e shared -r backend/requirements.txt   # 이미 있으면 requirements만 다시

# 1) 실행 계정 (없으면)
sudo useradd --system --home-dir /opt/game-nuri --shell /sbin/nologin backend

#    레포를 홈 등에서 옮겼다면 SELinux 라벨 복원이 필수다(없으면 서비스가 203/EXEC Permission denied, 아래 문제 해결)
sudo restorecon -Rv /opt/game-nuri

# 2) 환경 파일 — 값은 직접 채운다 (커밋 금지)
sudo mkdir -p /etc/game-nuri                 # 이미 있으면 그대로 둔다
sudo install -m 0640 -o root -g backend /opt/game-nuri/repo/infra/backend/systemd/backend.env.example /etc/game-nuri/backend.env
sudoedit /etc/game-nuri/backend.env        # SERVER_NAME은 서버에 맞게 backend1 / backend2

# 3) 서비스 등록·시작
sudo cp /opt/game-nuri/repo/infra/backend/systemd/backend.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now backend
```
`backend` 사용자가 `/opt/game-nuri/repo`(코드·venv)를 읽을 수 있어야 한다.

## 확인
```bash
systemctl status backend --no-pager
journalctl -u backend -n 50 --no-pager
curl -s http://localhost:8000/api/health         # status: ok | degraded (Primary가 안 되면 503)
curl -s http://localhost:8000/metrics | head     # Prometheus가 읽는 지표
```
`/api/health` 해석: `db_write`가 `ok`여야 하고, `db_read`·`valkey`·`es`가 안 되면 200 + `degraded`다(ES는 설치 전이라 `degraded`가 정상일 수 있다).
다른 서버에서: `curl -s http://backend1:8000/api/health` (backend2도).

## 코드를 업데이트할 때 (배포)
```bash
# git은 backend 계정으로 실행한다. `sudo git ...`(root)은 쓰지 않는다.
sudo -u backend -H git -C /opt/game-nuri/repo pull --rebase origin main
sudo systemctl restart backend && journalctl -u backend -n 30 --no-pager
curl -s http://localhost:8000/api/health
```
- **`sudo git pull`을 쓰지 않는 이유**: root로 실행하면 `.git`과 작업 파일의 소유자가 root로 바뀌어 이후 `backend` 계정의 `git pull`이 권한 오류로 막힐 수 있다.
- `backend/requirements.txt`가 바뀐 배포일 때만 패키지를 다시 설치한다: `sudo -u backend -H /opt/game-nuri/repo/.venv/bin/pip install -e shared -r backend/requirements.txt` (이 줄은 아직 서버에서 실행해 확인하지 않았다).
- DB 칸이 늘어나는 변경(예: `variant_name`)은 **DB에 칸을 먼저 추가한 뒤** 코드를 배포한다. 반대 순서면 조회가 오류를 낸다.

## 문제 해결
**`status=203/EXEC`, `Unable to locate executable '…/.venv/bin/…': Permission denied`**
- 원인: SELinux(Rocky 기본 Enforcing)가 `systemd`(`init_t`)의 실행을 막는다. 레포를 홈 디렉터리에서 `mv`로 `/opt`에 옮기면 파일 라벨이 `user_home_t`로 남는다(`ls -lZ`로 확인, `ausearch -m avc`에 `denied { execute } … user_home_t`).
- 해결: `sudo systemctl stop backend && sudo restorecon -Rv /opt/game-nuri && sudo systemctl start backend` (라벨만 기본값으로 되돌리고 파일 내용은 바꾸지 않는다. 기본값에서 `.venv/bin`은 `bin_t`가 된다).
- 예방: 레포는 `/opt/game-nuri`에서 직접 `git clone` 하거나, 옮긴 뒤에는 항상 `restorecon -Rv /opt/game-nuri`를 한다. SELinux를 끄지 않는다.
- 같은 이유로 수집 서버(proxy)·kafka1~3의 서비스도 시작이 막힐 수 있다.

**`/api/health`가 `degraded`**
- `es: down`: ES 주소·계정을 먼저 보고, **파이썬 `elasticsearch` 패키지 버전**도 확인한다. 서버가 ES 8.x인데 패키지가 9.x면 주소·계정이 맞아도 `down`이 나온다(그래서 `requirements.txt`가 `elasticsearch>=8.12,<9`로 고정돼 있다). `.venv/bin/pip show elasticsearch`로 본다.
- `db_read`가 `down`이면 Replica 접속(계정·`10.0.1.%` 허용 범위)을 확인한다. 앱은 Primary로 대신 읽는다.

## 알아둘 것
- **로그인**: 구글 로그인(`/api/auth/google/login`, `/api/auth/google/callback`)이 있다. 설정은 `backend.env`의 `GOOGLE_CLIENT_ID`·`GOOGLE_CLIENT_SECRET`·`GOOGLE_REDIRECT_URI`·`SESSION_SECRET`(이름만 `backend.env.example`에 있다, 값은 서버에만). `GOOGLE_REDIRECT_URI`는 구글 콘솔에 등록한 값과 한 글자도 다르면 안 된다. `SESSION_SECRET`은 backend1·backend2가 같은 값이어야 한다.
- **`AUTH_FAKE_USER`는 운영에서 반드시 `false`.** `true`이면 로그인 없이 `AUTH_FAKE_USER_ID` 사용자로 동작한다(시험용). 켜면 시작 로그에 경고가 남는다. 바꾼 뒤에는 `sudo systemctl restart backend`.
- **AI 사양 판정**(`/api/games/{id}/spec-check`): `GEMINI_API_KEY`와 `AI_MODEL`이 둘 다 있어야 한다. 하나라도 비면 503이고 화면은 사양 표만 보여 준다. Backend → Google AI(HTTPS 443) 나가는 연결이 되어야 한다. 키는 서버 `backend.env`에만 넣고 코드·문서·로그에 쓰지 않는다. (다른 AI 기능은 Backend에서 부르지 않는다. 리뷰 요약은 읽기만 한다.)
- 프로세스를 1개로 띄운다(`--workers` 없음). `/metrics`가 워커별로 갈라져 API 사용 순위(#37)가 틀어지는 것을 피하려는 것이다.
- `/api/stats/api-ranking`은 `infra/monitoring/prometheus.yml`에 `backend1:8000`, `backend2:8000` `/metrics` 수집 job이 있어야 값이 나온다(없으면 `degraded`, 남현식 폴더).
- 종료할 때 Kafka에 아직 안 나간 clickstream 메시지를 보내느라 최대 5초 걸린다(`TimeoutStopSec=15`).
- 아직 backend1·frontend1만 운영한다. backend2·frontend2는 기능이 갖춰진 뒤 배포한다(팀 합의).

## 확인되지 않은 것
- **backend1**: 구글 로그인, 구매 타이밍, 리뷰 API가 서버에서 동작하는 것을 확인했다.
- **미확인**: AI 사양 판정(서버의 `GEMINI_API_KEY`·`AI_MODEL`과 Google AI로 나가는 연결), backend2 전체, 위의 `pip install` 줄을 `backend` 계정으로 실행했을 때의 권한.
