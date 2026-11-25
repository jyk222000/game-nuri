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
> <- **`--askpass` 는 `| grep` 같은 파이프, 여러 줄 붙여넣기와 같이 쓰지 않습니다.** 비밀번호 안내 문구가 파이프로 들어가 화면에 안 보이고, 명령이 입력을 기다리며 멈춘 것처럼 됩니다(11/25에 겪음). 대화형으로 접속해서 한 줄씩 입력합니다. 아래 5번 참고.
> <- Backend는 `/etc/game-nuri/backend.env` 의 `VALKEY_URL=redis://:<비밀번호>@valkey:6379/0` 로 접속합니다. [05-backend.md](05-backend.md) 참고.

## 5. 상태 점검 (운영 중 확인)
대화형으로 접속해서 한 줄씩 입력합니다(파이프 없음).
```
# valkey VM 에서 — 비밀번호를 한 번 물어보고 프롬프트(127.0.0.1:6379>)가 나온다
[admina@valkey ~]$ valkey-cli --askpass -h 127.0.0.1

# 아래는 프롬프트 안에서 입력
127.0.0.1:6379> INFO memory
127.0.0.1:6379> INFO stats
127.0.0.1:6379> INFO server
127.0.0.1:6379> quit
```
> <- 볼 값: `used_memory_human`, `maxmemory_human`(256M), `maxmemory_policy`(allkeys-lru), `keyspace_hits`/`keyspace_misses`, `evicted_keys`, `expired_keys`, `uptime_in_seconds`.
> <- 키 개수는 목록을 화면에 띄우지 않고 센다: `valkey-cli --askpass -h 127.0.0.1 --scan --pattern 'session:*'` 의 출력이 세션 ID이므로 **개수만 본다**(프롬프트 안에서는 `DBSIZE`).
> <- `KEYS *` 는 쓰지 않습니다(키가 많으면 서버가 멈춤). 목록이 필요하면 `--scan` 을 씁니다.

**2026-11-25 점검 결과** (valkey VM, 가동 약 2일)
| 항목 | 값 | 해석 |
|---|---|---|
| 버전 | valkey 8.1.10 (Redis 7.2.4 호환 표기), standalone, systemd 실행 | 설치 기록과 같음 |
| 메모리 | 사용 1.11MB / 최대 256MB, 정책 allkeys-lru | 여유 충분 |
| `evicted_keys` | 0 | 메모리 부족으로 지운 키 없음 |
| `expired_keys` | 251 | TTL 만료로 자동 삭제된 키(캐시·알림 키가 수명대로 정리됨) |
| `keyspace_hits` / `misses` | 1641 / 259 | 적중률 약 86% |
| `rejected_connections` | 0 | 접속 거부 없음 |
| 누적 명령 | 66,322개, 접속 48회 | |

> <- 적중률 계산: 1641 ÷ (1641 + 259) ≈ 86.4%. 이 수치는 **세션 조회·가격 캐시·알림 키 확인을 모두 합친 값**이라 "가격 캐시만의 적중률"이 아닙니다.
> <- `used_memory_rss`(14MB)와 `mem_fragmentation_ratio`(12.69)는 사용량이 1MB대로 작아서 비율이 크게 나오는 것입니다. 이상이 아닙니다.
> <- `acl_access_denied_auth: 1`, `total_error_replies: 36`: 인증 실패 1회와 오류 응답 36건이 누적돼 있습니다. 원인(NOAUTH 확인 시험, 잘못 입력한 비밀번호 등)은 **미확인**입니다. 반복해서 늘어나면 원인을 봅니다.

## 6. Valkey 가 하는 일과 도입 이유 (발표용)
**하는 일** — Backend 1·2가 함께 쓰는 **공용 메모리 저장소**입니다. 원본 데이터는 두지 않고, 언제든 다시 만들 수 있는 사본만 둡니다.
| 용도 | 키 | 동작 |
|---|---|---|
| 로그인 세션 | `session:{id}` | 구글 로그인 후 쿠키의 세션 ID로 사용자(user_id)를 찾는다. 접속할 때마다 7일로 연장 |
| 가격 조회 캐시 | `cache:prices:{game_id}` | 같은 게임의 가격 비교 결과를 10분 동안 메모리에서 응답 |
| 실시간 검색어 캐시 | `cache:search:trending` | ES 집계 결과를 60초 재사용해 ES 호출을 줄임 |
| AI 사양 판정 | `spec_check:{game_id}:{사양 hash}` | 같은 게임·같은 사양이면 AI를 다시 부르지 않고 7일간 저장된 결과를 씀 |
| 알림 중복 방지 | `alert_sent:{alert_id}:{가격}` | 메일을 보내기 전에 `SET NX` 로 키를 먼저 잡아, 같은 가격으로 같은 메일이 두 번 나가지 않게 함 |

```
사용자 → Backend → ① Valkey 에 있나? ──있음──▶ 바로 응답
                      │없음
                      └─ ② MariaDB Replica / ES 조회 → ③ Valkey 에 저장(수명 설정) → 응답
```

**도입 이유**
1. **Backend가 2대라서 공유할 곳이 필요합니다.** 세션을 각 서버 메모리에 두면 backend1에서 로그인한 사용자가 backend2로 가는 순간 로그아웃됩니다. Valkey에 두면 두 서버가 같은 세션을 봅니다(`SESSION_SECRET` 도 두 서버가 같은 값).
2. **DB와 ES의 부담, 응답 시간을 줄입니다.** 자주 조회되지만 몇 분 단위로만 바뀌는 데이터(가격, 실시간 검색어)를 메모리에서 바로 응답합니다.
3. **AI 호출을 줄입니다.** 팀 규칙 "AI는 사용자 요청마다 부르지 않는다"를 지키는 수단입니다. 한 번 판정한 결과를 저장해 재사용합니다.
4. **중복 메일을 막습니다.** 알림 발송이 동시에 두 번 실행돼도 먼저 키를 잡은 쪽만 보냅니다.
5. **유실돼도 되는 것만 둡니다.** 저장이 필요한 데이터(사용자, 알림, 가격)는 MariaDB·MongoDB에 있습니다. 그래서 디스크 저장을 끄고 속도와 단순함을 택했습니다(재시작하면 비워짐).
6. **별도 VM으로 둔 이유**: Backend가 서버 수와 관계없이 같은 저장소를 보게 하고, Backend 재배포·재시작에도 세션이 유지되게 하기 위함입니다(`docs/decisions.md` 11/18 "Valkey 별도 VM — 가용성·공유 상태").
7. **Redis 대신 Valkey인 이유(보조 설명)**: Redis에서 갈라져 나온 오픈소스 포크라 명령·프로토콜이 같아 `redis-py` 를 그대로 쓰고, Rocky Linux 10 기본 저장소에 있어 `dnf` 로 바로 설치됩니다. ⚠ 팀이 이 이유로 결정했다는 기록은 없습니다.

**발표 때 짚을 점**
- 지금 운영은 **backend1만**이고 backend2는 배포 전입니다. "2대 공유"는 설계 이유입니다.
- Valkey를 재시작하면 세션이 비워져 **모든 사용자가 로그아웃**됩니다. 발표 직전에는 재시작하지 않습니다.
- 장애 시: Valkey가 꺼져도 사이트는 멈추지 않습니다(가격 캐시는 DB에서 직접 읽음, 로그인 확인은 익명으로 처리, `/api/health` 는 `degraded`).

## 7. Backend 에서의 동작 (알아둘 것)
- Valkey가 죽어도 사이트가 멈추지 않게 만들어져 있습니다. 가격 캐시는 **fail-open**(캐시를 못 쓰면 DB에서 직접 읽음)이고, `/api/health` 는 Valkey가 안 되면 `degraded` 로 응답합니다(서비스는 계속).
- 로그인 세션은 Valkey에 있으므로 **Valkey를 재시작하면 모든 사용자가 로그아웃**됩니다.

## 8. 확인됨 / 미확인
- 확인됨(11/25): `valkey.service` active, 인증 PING `PONG`, maxmemory 256MB·allkeys-lru, 가동 약 2일, `evicted_keys` 0, 적중률 약 86%(5번 표).
- 확인됨(11/22): backend IP가 그대로 보입니다. `CLIENT LIST` 에서 backend1의 출발지는 `10.0.1.103` 이고 게이트웨이 NAT는 없습니다.
- ⚠ 미확인: backend2의 출발지 IP(`CLIENT LIST`). backend2 인증 PING은 `True` 로 확인했습니다.
- ⚠ 미확인: Prometheus에서 Valkey 메트릭을 수집할지(별도 exporter 필요).
