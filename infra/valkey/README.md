# valkey

Backend의 캐시·세션·실시간 검색어·알림 중복 방지용 Valkey. 비밀번호는 이 문서에 쓰지 않는다.
(구축 2026-11-22, Jira NW2-21)

## 서버 정보
| 항목 | 값 |
|---|---|
| 호스트 | `valkey` (10.0.2.107, PC-2) |
| OS | Rocky Linux 10.1, SELinux Enforcing |
| 패키지 | `valkey 8.1.10-2.el10_3` (AppStream, `dnf install valkey`) |
| 서비스 | `valkey.service` (systemd, enable됨) |
| 포트 | 6379 |
| 설정 | `/etc/valkey/valkey.conf` (원본 백업 `valkey.conf.orig`) — 예시는 `valkey.conf.example` |
| 메모리 | VM RAM 약 1GB → `maxmemory 256mb` |

## 설정 요점
- `bind 0.0.0.0` + `requirepass` + `protected-mode yes`
- `maxmemory 256mb`, `maxmemory-policy allkeys-lru` (캐시이므로 가득 차면 오래된 키 삭제)
- `save ""`, `appendonly no` → 디스크에 저장하지 않는다. **재시작하면 데이터가 비워진다.**
  - 유실돼도 되는 것만 둔다: 가격 캐시(10분), 세션, 실시간 검색어, 알림 중복 방지 키.
- 비밀번호: 서버의 `valkey.conf`에만 있다. Backend는 `/etc/game-nuri/backend.env`의 `VALKEY_URL`로 받는다.

## 방화벽
**내부망 신뢰, 게이트웨이에서 제어, 보호는 `requirepass`.** (2026-11-22 결정: 내부 VM은 firewalld를 끈다.)
- valkey VM의 firewalld는 2026-11-22 23:13에 `systemctl disable --now firewalld`로 껐다 (`disabled`/`inactive` 확인).
- 처음에는 firewalld로 6379를 `10.0.1.0/24`·`10.0.2.0/24`에만 열었으나(rich rule), 위 결정에 맞춰 껐다.
  끄기 전 규칙은 이 문서에 남기지 않는다. 필요하면 `systemctl enable --now firewalld` 후 다시 설정한다.
- 접속은 비밀번호가 없으면 `NOAUTH`로 거부된다. 비밀번호는 서버의 `valkey.conf`에만 둔다.
- 방화벽 해제 후 PING 재확인(11/22): valkey `active`, `0.0.0.0:6379` listen. backend1·backend2 모두 인증 PING `True`, backend1 포트 OPEN 확인.

## 설치 중 확인된 것
- 설치 전 `/` 8GB 중 91% 사용. 원인은 `/var/cache/PackageKit` 1.7GB.
  `/var/cache/PackageKit/10.1/{metadata,hawkey}`를 지우고 `packagekit` 서비스를 mask해 2.4GB 확보했다.
  GUI 패키지는 설치돼 있지만 `multi-user.target`이라 실행되지 않는다(제거하지 않음).

## 접속 확인
비밀번호는 명령줄에 쓰지 않는다. 프롬프트로 입력한다.
```bash
# valkey VM 안에서
valkey-cli --askpass -h 127.0.0.1 PING          # PONG
valkey-cli --askpass -h 127.0.0.1 CONFIG GET maxmemory-policy   # allkeys-lru

# backend1에서 (valkey-cli는 설치하지 않는다. 포트 확인 + redis-py)
timeout 3 bash -c '</dev/tcp/valkey/6379' && echo OPEN
python - <<'EOF'
import getpass, redis
r = redis.Redis(host="valkey", port=6379, password=getpass.getpass(), socket_timeout=3)
print(r.ping())   # True
EOF
```
- 2026-11-22 backend1에서 포트 OPEN, `PING` True 확인 (방화벽 해제 후 backend1·2 재확인 포함).
- 정상: `PONG`/`True`. 비밀번호 없이 접속하면 `NOAUTH`가 나온다(정상).

## 확인됨
- 출발지 IP 확인(11/22): backend IP 그대로 보인다. `CLIENT LIST`에서 backend1의 출발지는 `10.0.1.103`(laddr `10.0.2.107:6379`)이고 게이트웨이 NAT는 없다. **backend1 기준이며 backend2는 `CLIENT LIST`로 확인하지 않았다.**

## 미확인
- backend2의 출발지 IP (`CLIENT LIST`의 `addr`). backend2 인증 PING은 `True`로 확인했다.
- Prometheus(PC-2)에서 Valkey 메트릭을 수집할지(별도 exporter 필요). 방화벽은 꺼져 있어 접속 자체는 가능하다.
