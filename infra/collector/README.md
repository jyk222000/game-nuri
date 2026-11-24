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
| `ES_URL`, `ES_USER`, `ES_PASSWORD` | 리뷰 요약 배치가 ES `reviews`를 집계할 때 (`ES_URL`을 빼면 localhost라 실패) |
| `GEMINI_API_KEY`, `AI_MODEL` | 리뷰 요약 배치의 AI 요약. 사양 판정(backend)과 같은 키·프로젝트라 무료 한도를 같이 쓴다 |

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

**리뷰 요약 배치(`python -m collector.review_summary`)는 이 표에 없다.** 타이머 없이 손으로 실행한다(아래 '리뷰 요약 배치'). 표의 `steam-review-summary`는 Steam의 리뷰 통계(GetItems)를 `raw.steam`으로 수집하는 다른 프로그램이다.

## 겹쳐 실행되지 않게 (다나와는 한 번에 2~3시간)
1. 서비스가 `Type=oneshot`이라 실행 중인 같은 서비스는 새 시작 요청이 합쳐진다(두 번 뜨지 않는다).
2. `run-collector.sh`가 이름별 `flock`을 잡는다. 이미 돌고 있으면 "건너뜀"만 로그에 남기고 정상 종료한다(손으로 실행 중일 때도 마찬가지).
3. `TimeoutStartSec=6h`로 멈춘 실행이 계속 남지 않게 한다. 다나와는 6시간 간격이라 보통 겹치지 않는다.
4. 시작 시 놓친 실행을 몰아서 돌리지 않는다(`Persistent` 미사용). 재부팅 후에는 다음 시각부터 돈다.

## 설치 (proxy에서, 한 번)
```bash
# 0) 스냅샷을 찍는다. 레포는 /opt/game-nuri/repo, venv는 /opt/game-nuri/repo/.venv (pip install -e shared -r collector/requirements.txt)
sudo useradd --system --home-dir /opt/game-nuri --shell /sbin/nologin collector   # 이미 있으면 생략
sudo restorecon -Rv /opt/game-nuri           # 레포를 홈 등에서 옮겼다면 필수(SELinux 라벨). 없으면 서비스가 203/EXEC Permission denied
sudo mkdir -p /etc/game-nuri                 # 이미 있으면 그대로 둔다
sudo install -m 0755 /opt/game-nuri/repo/infra/collector/run-collector.sh /usr/local/bin/run-collector.sh
sudo install -m 0640 -o root -g collector /opt/game-nuri/repo/infra/collector/systemd/collector.env.example /etc/game-nuri/collector.env
sudoedit /etc/game-nuri/collector.env        # 값 채우기 (커밋 금지)
sudo cp /opt/game-nuri/repo/infra/collector/systemd/collector@.service /opt/game-nuri/repo/infra/collector/systemd/collector-*.timer /etc/systemd/system/
sudo systemctl daemon-reload
```
`collector` 사용자가 `/opt/game-nuri/repo`를 읽고 `collector/samples`에 쓸 수 있어야 한다(`--dry-run`용). `samples/`는 소유자가 개인 계정이고 `collector`는 `gamenuri` 그룹에도 속하지 않아 기본으로는 쓸 수 없으므로, 그 폴더 하나에만 쓰기 권한을 준다(ACL, 소유자·그룹은 바꾸지 않는다). `git pull`로는 풀리지 않는다.
```bash
sudo setfacl -m u:collector:rwx /opt/game-nuri/repo/collector/samples
getfacl /opt/game-nuri/repo/collector/samples      # user:collector:rwx 가 보이면 적용된 것
# 되돌리기: sudo setfacl -x u:collector /opt/game-nuri/repo/collector/samples
```

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

## 리뷰 요약 배치 (손으로 실행, 타이머 없음)
ES `reviews`의 키워드를 AI로 한두 문장으로 요약해 `refined.review_summary`로 보낸다(→ `review_summaries`). 코드는 `collector/collector/review_summary.py`다. 위 `.env`의 `ES_*`, `GEMINI_API_KEY`, `AI_MODEL`이 필요하다.

모든 명령은 `collector` 계정으로, 환경 파일을 읽어 실행한다(오래 걸리는 것은 `nohup ... &`로 백그라운드).
```bash
cd /opt/game-nuri/repo/collector

# 시험: 두 게임만, Kafka로 보내지 않고 samples/에 저장
sudo -u collector bash -c 'set -a; . /etc/game-nuri/collector.env; set +a; /opt/game-nuri/repo/.venv/bin/python -m collector.review_summary --game-ids 1877,17000 --no-ai --dry-run'

# 1단계: AI 없이 전체의 키워드·긍정률만 보냄 (약 17분, AI 한도를 쓰지 않음)
sudo -u collector bash -c 'set -a; . /etc/game-nuri/collector.env; set +a; nohup /opt/game-nuri/repo/.venv/bin/python -m collector.review_summary --no-ai > /tmp/review_summary_send1.log 2>&1 &'

# 2단계: AI 요약을 인기 순으로 나눠 채움. 호출 수 상한에 닿으면 멈추고 로그에 '--skip K'를 알려 준다
sudo -u collector bash -c 'set -a; . /etc/game-nuri/collector.env; set +a; nohup /opt/game-nuri/repo/.venv/bin/python -m collector.review_summary --ai-only --max-ai-calls 330 > /tmp/review_summary_ai1.log 2>&1 &'
# 다음 날: 직전 로그가 알려 준 K부터 이어서
sudo -u collector bash -c 'set -a; . /etc/game-nuri/collector.env; set +a; nohup /opt/game-nuri/repo/.venv/bin/python -m collector.review_summary --ai-only --max-ai-calls 330 --skip K > /tmp/review_summary_ai2.log 2>&1 &'
```
같은 `game_id`는 덮어쓰기라 다시 보내도 중복이 생기지 않는다. 끝나면 로그 끝의 `리뷰 요약 완료: N건 전송`, `Kafka 전송 결과: 성공 N, 실패 0`을 확인하고, `review_summaries`나 `/api/games/{id}/reviews/summary`로 반영을 본다.

**지킬 것**
- **AI 요약을 채운 뒤에는 `--no-ai`로 전체를 다시 보내지 않는다.** `--no-ai`는 요약 문장이 빈 메시지를 보내고, 같은 `game_id`는 덮어쓰기라 이미 있는 AI 요약이 지워진다. AI를 다시 돌릴 때는 `--ai-only`를 쓴다(AI가 실패한 게임은 보내지 않아 기존 요약을 지키지 않는다).
- **무료 한도를 같이 쓴다.** Gemini 무료 등급(`gemini-3.5-flash-lite`, AI Studio 화면 기준 2026-11-25: 분당 15회, 하루 500회)이고 한도는 키가 아니라 프로젝트 단위라서 사양 판정(backend)과 나눠 쓴다. 배치는 호출 간격 6초(분당 최대 10회), 하루 330회 이하로 돌려 사양 판정 몫을 남긴다. 한도는 모델과 날짜에 따라 바뀔 수 있으니 AI Studio의 속도 제한 화면에서 다시 확인한다.
- **사양 판정을 시연하는 날에는 배치를 돌리지 않는다.** 한도를 사양 판정에 남겨 둔다.

**왜 타이머가 없나**
1. 전체를 AI로 요약하면 호출이 1,000번을 넘는다(실패 재시도 포함 약 1,100번). 하루 한도(500회)보다 많아서 며칠에 나눠 `--skip`으로 이어서 해야 하는데, 어디까지 했는지 기억하는 상태를 타이머가 갖고 있지 않다.
2. 리뷰는 하루에 수백 건(전체)만 늘어서 매일 요약을 새로 만들 이유가 작다.
3. 타이머가 `--no-ai`로 돌면 AI 요약이 지워진다(위 '지킬 것').

타이머가 필요해지면 호출 수 상한과 이어서 하기 상태를 어디에 둘지 정한 뒤에 만들고, 이름은 위 표의 `steam-review-summary`와 겹치지 않게 한다.

## 확인되지 않은 것
- 실제 VM에서의 실행은 아직 해 보지 않았다(파일만 작성). `collector` 계정·권한, venv 경로, 시간대는 서버에서 확인이 필요하다.
- `steam-review-summary`의 주기와 `STEAM_KEY` 필요 여부는 collector 담당이 정한다.
- 리뷰 요약 배치는 2026-11-25에 proxy에서 시험 전송(3개 게임)과 1단계 전체 전송을 했다. 2단계(AI 요약 전체)와 타이머는 아직 정하지 않았다.
