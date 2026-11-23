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
# 0) 스냅샷. 레포 최신화 + venv
cd /opt/game-nuri/repo && git pull
python3.12 -m venv .venv && .venv/bin/pip install -e shared -r backend/requirements.txt   # 이미 있으면 requirements만 다시

# 1) 실행 계정 (없으면)
sudo useradd --system --home-dir /opt/game-nuri --shell /sbin/nologin backend

# 2) 환경 파일 — 값은 직접 채운다 (커밋 금지)
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

## 코드를 업데이트할 때
```bash
cd /opt/game-nuri/repo && git pull
.venv/bin/pip install -e shared -r backend/requirements.txt
sudo systemctl restart backend && journalctl -u backend -n 30 --no-pager
```

## 알아둘 것
- **로그인(#1·#2)이 아직 없다.** 찜·알림·내 정보·Steam 연동 같은 로그인 API는 `AUTH_FAKE_USER=true`일 때만 시험할 수 있다. 켜면 시작 로그에 경고가 남는다. **시험 후 반드시 `false`로 되돌리고 `sudo systemctl restart backend`.**
- 프로세스를 1개로 띄운다(`--workers` 없음). `/metrics`가 워커별로 갈라져 API 사용 순위(#37)가 틀어지는 것을 피하려는 것이다.
- `/api/stats/api-ranking`은 `infra/monitoring/prometheus.yml`에 `backend1:8000`, `backend2:8000` `/metrics` 수집 job이 있어야 값이 나온다(없으면 `degraded`, 남현식 폴더).
- 종료할 때 Kafka에 아직 안 나간 clickstream 메시지를 보내느라 최대 5초 걸린다(`TimeoutStopSec=15`).

## 확인되지 않은 것
- 파일만 작성했고 VM에서 실행해 보지 못했다. `backend` 계정·권한, venv 경로(`/opt/game-nuri/repo/.venv`), 포트 8000 접근, MariaDB 서비스 계정 권한은 서버에서 확인이 필요하다.
