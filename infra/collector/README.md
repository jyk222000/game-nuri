# collector 실행 (수집 서버 = proxy)

수집기(`collector/`)를 systemd 타이머로 주기 실행한다. 코드는 `collector/`(한예찬), 실행 설정만 여기 둔다.
VM에서 하는 작업은 사용자가 직접 실행한다.

## .env에 필요한 값
`/etc/game-nuri/collector.env` (예시: `systemd/collector.env.example`, 권한 `root:collector 640`)

| 값 | 용도 |
|---|---|
| `KAFKA_BOOTSTRAP` | `raw.*` 발행 (예: `kafka1:9092,kafka2:9092,kafka3:9092`) |
| `TWITCH_CLIENT_ID`, `TWITCH_CLIENT_SECRET` | IGDB |
| `ITAD_KEY` | ITAD 가격·이력 |
| `STEAM_KEY` | 키가 필요한 Steam 호출용 (사양·리뷰·동접자는 불필요, GetItems 필요 여부 미확인) |

## 수집 종류와 주기 (OS 시간대 Asia/Seoul)
| 이름 | 명령 | 주기 | 시각 |
|---|---|---|---|
| `itad-price` | `--source itad --kind price` | 6시간 | 00·06·12·18:05 |
| `itad-history` | `--source itad --kind price_history --since-days 14` | 주 1회 | 일 02:00 |
| `igdb` | `--source igdb` | 매일 | 03:00 |
| `steam-details` | `--source steam --kind app_details` | 매일 | 04:00 |
| `steam-review-summary` | `--source steam --kind review_summary` | 매일(임시) | 04:30 |
| `steam-reviews` | `--source steam --kind review` | 매일 | 05:00 |
| `steam-players` | `--source steam --kind player_count` | 1시간 | 매시 20분 |
| `danawa` | `--source danawa` | 6시간 | 00·06·12·18:30 |

시각을 나눈 이유: 같은 VM에서 여러 수집이 한꺼번에 돌지 않게 하려는 것이다. 주기는 `collector/CLAUDE.md` 기준이고, 바꾸려면 해당 `.timer`의 `OnCalendar`만 고친다.

## 겹쳐 실행되지 않게 (다나와는 한 번에 2~3시간)
1. 서비스가 `Type=oneshot`이라 실행 중인 같은 서비스는 새 시작 요청이 합쳐진다(두 번 뜨지 않는다).
2. `run-collector.sh`가 이름별 `flock`을 잡는다. 이미 돌고 있으면 "건너뜀"만 로그에 남기고 정상 종료한다(손으로 실행 중일 때도 마찬가지).
3. `TimeoutStartSec=6h`로 멈춘 실행이 계속 남지 않게 한다. 다나와는 6시간 간격이라 보통 겹치지 않는다.
4. 시작 시 놓친 실행을 몰아서 돌리지 않는다(`Persistent` 미사용). 재부팅 후에는 다음 시각부터 돈다.

## 설치 (proxy에서, 한 번)
```bash
# 0) 스냅샷을 찍는다. 레포는 /opt/game-nuri/repo, venv는 /opt/game-nuri/repo/.venv (pip install -e shared -r collector/requirements.txt)
sudo useradd --system --home-dir /opt/game-nuri --shell /sbin/nologin collector   # 이미 있으면 생략
sudo install -m 0755 /opt/game-nuri/repo/infra/collector/run-collector.sh /usr/local/bin/run-collector.sh
sudo install -m 0640 -o root -g collector /opt/game-nuri/repo/infra/collector/systemd/collector.env.example /etc/game-nuri/collector.env
sudoedit /etc/game-nuri/collector.env        # 값 채우기 (커밋 금지)
sudo cp /opt/game-nuri/repo/infra/collector/systemd/collector@.service /opt/game-nuri/repo/infra/collector/systemd/collector-*.timer /etc/systemd/system/
sudo systemctl daemon-reload
```
`collector` 사용자가 `/opt/game-nuri/repo`를 읽고 `collector/samples`에 쓸 수 있어야 한다(`--dry-run`용).

## 먼저 한 번 손으로 (타이머를 켜기 전)
```bash
sudo systemctl start collector@steam-players.service     # 가장 가벼운 것부터
journalctl -u collector@steam-players.service -n 50 --no-pager
```
결과가 정상(Kafka `raw.steam`에 메시지가 쌓임, `python scripts/verify_flow.py`)이면 타이머를 켠다.
```bash
sudo systemctl enable --now collector-steam-players.timer     # 종류별로 하나씩
systemctl list-timers 'collector-*'
```
IGDB → Steam → ITAD → 다나와 순서로 켠다(refiner의 게임 ID 대응표가 앞 출처에서 배운다, `pipeline/refiner/README.md`).

## 확인되지 않은 것
- 실제 VM에서의 실행은 아직 해 보지 않았다(파일만 작성). `collector` 계정·권한, venv 경로, 시간대는 서버에서 확인이 필요하다.
- `steam-review-summary`의 주기와 `STEAM_KEY` 필요 여부는 collector 담당이 정한다.
