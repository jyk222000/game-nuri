# 겜누리 구축 워크북 — 1부: 기본 서버 · 네트워크

> 전 프로젝트("오늘 뭐 먹지") 워크북의 방식(Rocky Linux 10, VirtualBox 내부 네트워크 + 게이트웨이 VM, nmcli, iptables)을
> 겜누리 VM 17대에 맞춘 것. **이 1부가 끝나야 팀원들이 서버를 쓸 수 있다.** 서비스별 설치(MariaDB, MongoDB, ELK …)는 2부에서.
> IP·호스트 이름의 기준은 `docs/network.md`. 비밀번호는 이 문서에 쓰지 않는다.

## 0. 한눈에

```
                         교실 공유기망 192.168.0.0/24 (GW 192.168.0.1)
              ┌──────────────────────────┴──────────────────────────┐
     proxy 192.168.0.222 (enp0s3, 브리지)              monitor 192.168.0.223 (enp0s3, 브리지)
     10.0.1.1 (enp0s8, 내부 pc1-net) = PC-1 게이트웨이     10.0.2.1 (enp0s8, 내부 pc2-net) = PC-2 게이트웨이
              │                                                   │
   PC-1 내부망 10.0.1.0/24                              PC-2 내부망 10.0.2.0/24
   fe1 .11  fe2 .12  be1 .21  be2 .22                   mariadb-p .51  mariadb-r .52
   kafka1 .31  kafka2 .32  kafka3 .33  backup .40       mongo1 .61  mongo2 .62  mongo3 .63
                                                        elk .71  valkey .81
```

- **공인 IP(0번대)를 쓰는 VM은 proxy, monitor 두 대뿐.** 이 둘만 어댑터 2개(브리지 + 내부 네트워크), 나머지 15대는 **어댑터 1개(내부 네트워크)**.
- VirtualBox 내부 네트워크는 **PC 한 대 안에서만** 통한다. 그래서 PC마다 내부망을 하나씩 두고, 두 게이트웨이(proxy ↔ monitor)가 서로의 내부망으로 **라우팅**해 준다.
  - 예: kafka1(10.0.1.31) → proxy → 192.168.0.223(monitor) → mariadb-p(10.0.2.51). Kafka → DB 적재가 이 길로 간다.
- 인터넷은 각 PC의 게이트웨이가 **NAT**로 내보낸다 (dnf 설치, 수집기의 외부 API 호출).
- 외부에서 들어오는 길은 proxy(서비스 80/443)와 monitor(Grafana 3000, 관리용 SSH) 두 곳뿐. DB·Kafka는 외부에서 직접 닿지 않는다.

## 1. VirtualBox 설정

### 1-1. VM 공통
| 항목 | 값 |
|---|---|
| OS | Rocky Linux 10 (Minimal 또는 Server, GUI 없이) |
| 메모리·CPU·디스크·파티션 | `docs/network.md` 아래 "VM 사양" 표 (팀원이 만든 VM 구성 그대로) |
| 오디오·USB | 끔 |
| 설치 시 계정 | root 비밀번호 설정, 관리자 계정 `gnadmin`(wheel) 1개 — 팀원 계정은 3-5에서 |

### 1-2. 어댑터
| VM | 어댑터 1 (enp0s3) | 어댑터 2 (enp0s8) |
|---|---|---|
| proxy | 브리지 (공유기망 랜카드) | 내부 네트워크 `pc1-net` |
| monitor | 브리지 (공유기망 랜카드) | 내부 네트워크 `pc2-net` |
| PC-1의 나머지 8대 | 내부 네트워크 `pc1-net` | – |
| PC-2의 나머지 7대 | 내부 네트워크 `pc2-net` | – |

- 내부 네트워크 이름은 **대소문자까지 같아야** 같은 망이 된다.
- 지금 VM에 걸린 **호스트 전용 어댑터(192.168.56.x)는 지운다.** 두 PC를 잇지 못하고 인터넷도 안 된다.
- 어댑터 이름(enp0s3/enp0s8)은 VM마다 `nmcli con show`로 먼저 확인한다.

### 1-3. VM을 복제해서 만들 때 (한 대 세팅 → 나머지 복제)
복제본은 아래를 꼭 바꾼다. 안 바꾸면 IP·SSH가 꼬인다.
```bash
sudo hostnamectl set-hostname <새 이름>
sudo nmcli con mod enp0s3 802-3-ethernet.mac-address ""
sudo rm -f /etc/machine-id && sudo systemd-machine-id-setup
sudo rm -f /etc/ssh/ssh_host_* && sudo ssh-keygen -A
```
복제 시 VirtualBox에서 "모든 네트워크 어댑터의 새 MAC 주소 생성"을 고른다.

## 2. 고정 IP (nmcli)

### 2-1. 게이트웨이: proxy (PC-1)
```bash
sudo hostnamectl set-hostname proxy
sudo nmcli con mod enp0s3 ipv4.method manual ipv4.addresses 192.168.0.222/24 ipv4.gateway 192.168.0.1 \
  ipv4.dns "8.8.8.8 1.1.1.1" ipv4.ignore-auto-dns yes ipv4.routes "10.0.2.0/24 192.168.0.223"
sudo nmcli con mod enp0s8 ipv4.method manual ipv4.addresses 10.0.1.1/24 ipv4.never-default yes ipv4.dns "" ipv4.ignore-auto-dns yes
sudo nmcli con up enp0s3 && sudo nmcli con up enp0s8
```

### 2-2. 게이트웨이: monitor (PC-2)
```bash
sudo hostnamectl set-hostname monitor
sudo nmcli con mod enp0s3 ipv4.method manual ipv4.addresses 192.168.0.223/24 ipv4.gateway 192.168.0.1 \
  ipv4.dns "8.8.8.8 1.1.1.1" ipv4.ignore-auto-dns yes ipv4.routes "10.0.1.0/24 192.168.0.222"
sudo nmcli con mod enp0s8 ipv4.method manual ipv4.addresses 10.0.2.1/24 ipv4.never-default yes ipv4.dns "" ipv4.ignore-auto-dns yes
sudo nmcli con up enp0s3 && sudo nmcli con up enp0s8
```
- `ipv4.routes`가 핵심: proxy는 "PC-2 내부망은 monitor로", monitor는 "PC-1 내부망은 proxy로" 보낸다.
- 내부 NIC(enp0s8)에는 게이트웨이·DNS를 넣지 않는다 (전 프로젝트에서 dnf DNS 오류의 원인).

### 2-3. 내부 VM 15대 (예: kafka1)
```bash
sudo hostnamectl set-hostname kafka1
sudo nmcli con mod enp0s3 ipv4.method manual ipv4.addresses 10.0.1.31/24 ipv4.gateway 10.0.1.1 \
  ipv4.dns "8.8.8.8 1.1.1.1" ipv4.ignore-auto-dns yes
sudo nmcli con up enp0s3
```
- PC-1 VM은 게이트웨이 `10.0.1.1`, PC-2 VM은 `10.0.2.1`. 주소는 `docs/network.md` 표대로.
- 스크립트로 하려면: `sudo bash infra/network/internal-vm.sh kafka1 10.0.1.31/24 10.0.1.1`

## 3. 공통 기본 설정 (17대 모두)

### 3-1. 포워딩 + 라우팅 + NAT — **proxy, monitor만**
```bash
sudo bash infra/network/gateway.sh pc1   # proxy에서
sudo bash infra/network/gateway.sh pc2   # monitor에서
```
스크립트가 하는 일 (직접 칠 때 순서):
1. `net.ipv4.ip_forward = 1` (`/etc/sysctl.d/99-forward.conf`)
2. FORWARD: 내 내부망 → 밖, 밖 → 내 내부망(응답), **두 내부망 사이(10.0.1.0/24 ↔ 10.0.2.0/24) 양방향 허용**
3. NAT: `-s <내 내부망> ! -d <상대 내부망> -o enp0s3 -j MASQUERADE` — 인터넷으로 나갈 때만 주소 변환, 두 내부망 사이는 변환하지 않음
4. INPUT: lo, 연결된 응답, ping, SSH(공유기망·두 내부망), 서비스 포트(proxy 80/443, monitor 3000) 허용 → 마지막에 정책 DROP

### 3-2. 방화벽 — 내부 VM 15대 (1부 단계)
```bash
sudo bash infra/network/internal-firewall.sh
```
- firewalld는 끄고(mask) iptables-nft로 관리한다 (전 프로젝트와 동일).
- **1부에서는 두 내부망(10.0.0.0/16)에서 오는 것은 전부 허용**, 그 밖은 차단한다. 팀원이 Kafka·DB 포트를 열어 달라고 기다리지 않게 하기 위해서다.
- 서비스별로 포트를 좁히는 것은 2부(각 서비스 설치 후)에서 한다.
- 저장은 반드시 `iptables-save` → 서비스 켜기 순서 (반대로 하면 기본 규칙이 덮어씀).

### 3-3. 패키지 · 시간 · 시간대
```bash
sudo dnf update -y
sudo dnf install -y chrony vim git tar wget curl net-tools bind-utils policycoreutils-python-utils iptables-nft-services
sudo systemctl enable --now chronyd
sudo timedatectl set-timezone Asia/Seoul    # 서버 로그 읽기용. 앱 데이터는 UTC로 저장 (CLAUDE.md)
```
- Kafka 복제·MongoDB 복제는 서버 시간이 어긋나면 문제가 생긴다. `chronyc tracking`으로 확인.

### 3-4. 호스트 이름 등록
```bash
sudo cp infra/hosts /tmp/gn-hosts && cat /tmp/gn-hosts | sudo tee -a /etc/hosts
```
- 17대 모두 같은 `/etc/hosts`. 코드와 설정에는 IP 대신 이 이름을 쓴다.

### 3-5. 팀원 계정 + SSH 키
```bash
for u in junyoung hyunsik goeun yechan; do sudo useradd -m -G wheel "$u"; done
# 각자 PC에서 만든 공개키를 넣는다 (비밀번호 로그인은 끔)
sudo mkdir -p /home/<user>/.ssh && sudo tee /home/<user>/.ssh/authorized_keys < <user>.pub
sudo chown -R <user>:<user> /home/<user>/.ssh && sudo chmod 700 /home/<user>/.ssh && sudo chmod 600 /home/<user>/.ssh/authorized_keys
```
- 키가 모두 들어간 뒤 `/etc/ssh/sshd_config`에서 `PasswordAuthentication no`, `PermitRootLogin no` → `sudo systemctl restart sshd`.
- 팀원 PC에서는 `infra/ssh/config.example`을 `~/.ssh/config`에 붙인다: PC-1 VM은 proxy를, PC-2 VM은 monitor를 거쳐 접속 (`ssh kafka1` 한 줄).

### 3-6. swap · 커널
```bash
echo 'vm.swappiness = 1' | sudo tee /etc/sysctl.d/99-swap.conf && sudo sysctl --system
```
- 모든 VM에 적용. ES·Kafka·DB가 swap으로 밀려 느려지는 것을 막는다. ES는 2부에서 `bootstrap.memory_lock: true`까지.

### 3-7. SELinux
- **enforcing 유지.** 대신 기본 위치가 아닌 데이터 경로는 2부에서 라벨을 붙인다:
  `sudo semanage fcontext -a -t mysqld_db_t "/DATA/mysql(/.*)?" && sudo restorecon -Rv /DATA/mysql` (MongoDB `mongod_var_lib_t`도 같은 방식)
- 막히면 `sudo ausearch -m avc -ts recent`로 원인부터 본다. 서버 전체 permissive는 쓰지 않는다.

### 3-8. Python
- Rocky 10의 기본 Python은 **3.12**다. 레포는 3.11 기준으로 적혀 있으므로 3.12로 통일할지 팀에서 정한다 (`docs/decisions.md`).

### 3-9. 스냅샷
- 3장까지 끝나면 17대 모두 VirtualBox 스냅샷 `base-ok`를 찍는다. 2부 설치가 꼬이면 여기로 되돌린다.

## 4. 확인 (모두 통과해야 1부 완료)
| 어디서 | 명령 | 정상 결과 |
|---|---|---|
| proxy, monitor | `sysctl net.ipv4.ip_forward` | `= 1` |
| proxy | `ip route` | `10.0.2.0/24 via 192.168.0.223` 한 줄 |
| monitor | `ip route` | `10.0.1.0/24 via 192.168.0.222` 한 줄 |
| 내부 VM 아무거나 | `ping -c 2 8.8.8.8` && `getent hosts rockylinux.org` | 응답 + IP 나옴 (NAT·DNS) |
| kafka1 | `ping -c 2 mariadb-p` | 응답 (PC-1 → PC-2 라우팅) |
| mongo1 | `ping -c 2 kafka3` | 응답 (PC-2 → PC-1 라우팅) |
| 팀원 PC | `ssh kafka1`, `ssh elk` | 접속됨 (점프 경유) |
| 모든 VM | `chronyc tracking` | `Leap status: Normal` |
| 공유기망 다른 PC | `ping 10.0.1.31` | **실패해야 정상** (내부망은 외부에서 안 보임) |

## 5. 끝나면 넘겨줄 것 (팀원이 기다리는 순서)
| 받는 사람 | 무엇 | 목표 |
|---|---|---|
| 남현식 | kafka1~3 (4장 통과 + `/DATA` 마운트 확인) | **11/20 오전** |
| 전원 | `infra/ssh/config.example`, 계정 접속 확인 | 11/20 오전 |
| 남현식·이고은 | mariadb-p, mongo1~3 주소 (2부 설치 후) | 11/21 |
| 한예찬 | proxy에서 외부 API 호출 가능 확인 | 11/22 전 |

## 겪을 수 있는 문제
| 증상 | 원인 | 해결 |
|---|---|---|
| 내부 VM에서 `ping 8.8.8.8`은 되는데 `dnf`가 안 됨 | DNS | 내부 VM은 `ipv4.dns "8.8.8.8 1.1.1.1"`, 게이트웨이의 enp0s8은 DNS 비움 |
| 같은 PC끼리는 되는데 PC-1 ↔ PC-2만 안 됨 | 게이트웨이 라우트 또는 FORWARD 규칙 누락 | 4장 `ip route` 확인, `iptables -S FORWARD`에 10.0.1.0/24 ↔ 10.0.2.0/24 두 줄 |
| PC-2 DB 로그에 출발지가 192.168.0.222로 찍힘 | NAT가 내부망 사이에도 걸림 | MASQUERADE에 `! -d <상대 내부망>`이 빠짐 → 다시 추가 |
| 내부망끼리 안 됨 | 내부 네트워크 이름 오타(대소문자) | VirtualBox 어댑터 이름 `pc1-net` / `pc2-net` 확인 |
| 복제한 VM끼리 IP 충돌, SSH 경고 | MAC·machine-id·호스트 키가 같음 | 1-3 실행, PC에서 `ssh-keygen -R <호스트>` |
| 재부팅 후 방화벽 규칙이 사라짐 | 저장 순서 | `iptables-save > /etc/sysconfig/iptables` 후 `systemctl enable --now iptables` |
