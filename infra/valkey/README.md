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

## 방화벽 (firewalld, public zone)
6379는 아래 두 대역에서만 허용한다.
```bash
sudo firewall-cmd --permanent --add-rich-rule='rule family="ipv4" source address="10.0.1.0/24" port port="6379" protocol="tcp" accept'
sudo firewall-cmd --permanent --add-rich-rule='rule family="ipv4" source address="10.0.2.0/24" port port="6379" protocol="tcp" accept'
sudo firewall-cmd --reload
```
- 10.0.1.0/24: Backend 1·2.
- 10.0.2.0/24: Prometheus 수집용(PC-2). 필요한 출발지가 `10.0.2.1`뿐이면 `/32`로 좁힐 수 있다.

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
- 2026-11-22 backend1에서 포트 OPEN, `PING` True 확인.
- 정상: `PONG`/`True`. 비밀번호 없이 접속하면 `NOAUTH`가 나온다(정상).

## 미확인
- Backend → Valkey 접속 시 Valkey가 보는 실제 출발지 IP (`CLIENT LIST`의 `addr`).
  backend1(10.0.1.103) 그대로인지 게이트웨이 IP인지.
- Prometheus(PC-2)에서 Valkey 메트릭을 수집할지(별도 exporter 필요). 현재는 방화벽만 열어 둠.
- backend2에서의 접속 확인(4단계 배포 때).
