# 3. Valkey (valkey VM)

Backend의 **세션, 가격 캐시, 실시간 검색어 캐시, AI 사양 판정 캐시, 알림 중복 방지 키**를 두는 메모리 저장소입니다.
Redis와 호환되는 오픈소스(Valkey)이고, Backend는 `redis-py`로 접속합니다. (구축 2026-11-22, `infra/valkey/README.md`가 원본 기록)

## 0. 만드는 것
| 항목 | 값 |
|---|---|
| 호스트 | `valkey` (10.0.2.107, PC-2) |
| OS | Rocky Linux 10.1, SELinux Enforcing |
| 패키지 | `valkey 8.1.10` (AppStream, `dnf install valkey`) |
| 서비스 | `valkey.service` (systemd) |
| 포트 | 6379 |
| 설정 | `/etc/valkey/valkey.conf` (예시는 `infra/valkey/valkey.conf.example`) |
| 메모리 | VM RAM 약 1GB → `maxmemory 256mb` |

Backend가 쓰는 키 (`backend/app/core/keys.py`):
| 키 | 내용 | 수명 |
|---|---|---|
| `session:{id}` | 로그인 세션(user_id) | 7일 |
| `cache:prices:{game_id}` | 가격 비교 결과 | 10분 |
| `cache:search:trending` | 실시간 검색어 | 60초 |
| `spec_check:{game_id}:{hash}` | AI 사양 판정 결과 | 7일 |
| `alert_sent:{alert_id}:{price}` | 목표가 알림 중복 방지 | 24시간 |

> <- **저장을 끄기 때문에 재시작하면 전부 사라집니다.** 사라져도 되는 것만 두는 것이 원칙입니다(세션이 사라지면 다시 로그인하면 됨).

## 1. 설치
```
# 대상 VM이 valkey 인지 확인
[admina@valkey ~]$ hostname

# Valkey 설치 (Rocky 10 기본 저장소)
[admina@valkey ~]$ sudo dnf install -y valkey

# 설치된 버전 확인
[admina@valkey ~]$ valkey-server --version
```
> <- 설치 전 디스크가 부족하면 `df -h /` 를 확인합니다. 이 VM은 `/` 8GB 중 91%였고 원인은 `/var/cache/PackageKit` 1.7GB였습니다.
> 아래처럼 지우고 `packagekit` 서비스를 막아 2.4GB를 확보했습니다.

```
# (디스크가 부족할 때만) 패키지 캐시 지우기 — 캐시라서 지워도 다시 만들어진다
[admina@valkey ~]$ sudo rm -rf /var/cache/PackageKit/10.1/metadata /var/cache/PackageKit/10.1/hawkey

# PackageKit 이 다시 캐시를 쌓지 않게 막기
[admina@valkey ~]$ sudo systemctl mask packagekit
```
> <- `⚠ 되돌릴 수 없음` 은 아니지만(캐시) 경로를 정확히 입력해야 합니다. `rm -rf` 는 입력 전에 한 번 더 읽습니다.

## 2. 설정
```
# 원본 설정 백업 (되돌릴 때 필요)
[admina@valkey ~]$ sudo cp /etc/valkey/valkey.conf /etc/valkey/valkey.conf.orig

# 설정 편집
[admina@valkey ~]$ sudoedit /etc/valkey/valkey.conf
```
바꿀 항목(예시는 `infra/valkey/valkey.conf.example`):
```
> bind 0.0.0.0
> protected-mode yes
> port 6379
> requirepass <서버에서 직접 입력>
> maxmemory 256mb
> maxmemory-policy allkeys-lru
> save ""
> appendonly no
```
> <- `bind 0.0.0.0`: 다른 VM(backend)이 접속하도록 모든 주소에서 받습니다. 대신 **`requirepass` 가 유일한 보호**입니다(방화벽을 껐기 때문).
> <- **비밀번호는 서버의 이 파일에만 씁니다.** 레포·채팅·명령줄에 쓰지 않습니다. 긴 임의 문자열로 정합니다.
> <- `maxmemory 256mb` + `allkeys-lru`: 가득 차면 오래 안 쓴 키부터 지웁니다(캐시라서 안전).
> <- `save ""`, `appendonly no`: 디스크에 저장하지 않습니다.

```
# 설정 파일 권한: 비밀번호가 들어 있으므로 일반 사용자가 못 읽게
[admina@valkey ~]$ sudo chown valkey:root /etc/valkey/valkey.conf
[admina@valkey ~]$ sudo chmod 640 /etc/valkey/valkey.conf

# 서비스 시작과 부팅 시 자동 시작
[admina@valkey ~]$ sudo systemctl enable --now valkey

# 상태 확인 (active (running))
[admina@valkey ~]$ systemctl status valkey --no-pager

# 6379 포트 LISTEN 확인 (0.0.0.0:6379)
[admina@valkey ~]$ sudo ss -tlnp | grep 6379
```

## 3. 방화벽
**내부망 신뢰, 게이트웨이에서 제어, 보호는 `requirepass`.** (2026-11-22 결정)
```
# valkey VM 의 firewalld 끄기 (11/22 23:13 에 실행)
[admina@valkey ~]$ sudo systemctl disable --now firewalld
[admina@valkey ~]$ systemctl is-active firewalld; systemctl is-enabled firewalld
```
> <- 결과가 `inactive` / `disabled` 이면 정상입니다(11/25에도 확인).

## 4. 접속 확인
비밀번호는 명령줄에 쓰지 않고 **프롬프트로 입력**합니다.
```
# (valkey VM 안에서) 연결 확인 — 비밀번호를 물어본다
[admina@valkey ~]$ valkey-cli --askpass -h 127.0.0.1 PING
> PONG

# 캐시 정책 확인
[admina@valkey ~]$ valkey-cli --askpass -h 127.0.0.1 CONFIG GET maxmemory-policy
> allkeys-lru

# (backend1 에서) 포트가 열려 있는지
[admina@backend1 ~]$ timeout 3 bash -c '</dev/tcp/valkey/6379' && echo OPEN

# (backend1 에서) 비밀번호로 접속되는지 (redis-py 사용, 입력창으로 받음)
[admina@backend1 ~]$ /opt/game-nuri/repo/.venv/bin/python -c "import getpass, redis; r = redis.Redis(host='valkey', port=6379, password=getpass.getpass(), socket_timeout=3); print(r.ping())"
> True
```
> <- 비밀번호 없이 접속하면 `NOAUTH` 가 나오는 것이 **정상**입니다(보호가 켜져 있다는 뜻).
> <- Backend는 `/etc/game-nuri/backend.env` 의 `VALKEY_URL=redis://:<비밀번호>@valkey:6379/0` 로 접속합니다. [05-backend.md](05-backend.md) 참고.

## 5. Backend 에서의 동작 (알아둘 것)
- Valkey가 죽어도 사이트가 멈추지 않게 만들어져 있습니다. 가격 캐시는 **fail-open**(캐시를 못 쓰면 DB에서 직접 읽음)이고, `/api/health` 는 Valkey가 안 되면 `degraded` 로 응답합니다(서비스는 계속).
- 로그인 세션은 Valkey에 있으므로 **Valkey를 재시작하면 모든 사용자가 로그아웃**됩니다.

## 6. 확인됨 / 미확인
- 확인됨(11/22): backend IP가 그대로 보입니다. `CLIENT LIST` 에서 backend1의 출발지는 `10.0.1.103` 이고 게이트웨이 NAT는 없습니다.
- ⚠ 미확인: backend2의 출발지 IP(`CLIENT LIST`). backend2 인증 PING은 `True` 로 확인했습니다.
- ⚠ 미확인: Prometheus에서 Valkey 메트릭을 수집할지(별도 exporter 필요).
