# 네트워크 · 호스트 · 포트

> **실제 값 (2026-11-20, VM 17대에 적용·확인).** 코드와 설정 파일에는 IP 대신 아래 **호스트 이름**을 쓴다.
> 17대의 `/etc/hosts`에는 이미 아래 이름이 들어가 있다. 이전 이름(fe1, be1, monitor, mariadb-p, mariadb-r,
> mongo1~3)은 쓰지 않는다. 이전 이름 블록을 `/etc/hosts`에 덧붙이지 않는다 (같은 IP에 이름이 두 개 생김).

## 구성
- OS: **Rocky Linux 10** (네트워크 nmcli, 방화벽 iptables-nft-services, firewalld 사용 안 함)
- VirtualBox. 구축용 PC 2대에 내부 네트워크를 하나씩 두고, PC마다 게이트웨이 VM 1대가 내부망과 공유기를 잇는다.
- 공유기 `192.168.0.1` (192.168.0.0/24). 게이트웨이 VM만 브리지 어댑터로 공유기에 붙는다.
- 내부 VM은 어댑터 1개(내부 네트워크)뿐이고, 기본 경로는 자기 PC의 게이트웨이다.

```
           공유기 192.168.0.1
            │                          │
  proxy 192.168.0.222            monitoring 192.168.0.223
  10.0.1.1 (pc1-net)             10.0.2.1 (pc2-net)
            │                          │
  PC-1 내부망 10.0.1.0/24        PC-2 내부망 10.0.2.0/24
```

| 항목 | PC-1 | PC-2 |
|---|---|---|
| VirtualBox 내부 네트워크 | `pc1-net` | `pc2-net` |
| 내부 대역 | 10.0.1.0/24 | 10.0.2.0/24 |
| 게이트웨이 VM | proxy (enp0s3 브리지 192.168.0.222, enp0s8 10.0.1.1) | monitoring (enp0s3 브리지 192.168.0.223, enp0s8 10.0.2.1) |
| 상대 PC로 가는 정적 경로 | `10.0.2.0/24 via 192.168.0.223` | `10.0.1.0/24 via 192.168.0.222` |
| 내부 VM DNS | 203.248.252.2, 164.124.101.2 (현재 값, 8.8.8.8·1.1.1.1로 통일할지 결정 필요) | 같음 |

게이트웨이·내부 VM 설정 스크립트는 `infra/network/`에 있다.

## 도메인
- 도메인: **`gamenuri.store`** (가비아에서 구입 완료, 네임서버는 가비아 기본값)
- 계획: A 레코드 `@ → 192.168.0.222` (proxy). 사설 IP라 강의실 LAN 안에서만 접속된다 (공유기 포트포워딩 없음).
- HTTPS: Let's Encrypt DNS-01(TXT 레코드 수동 입력)로 발급(2026-11-20, 만료 2027-02-18) → HAProxy 443에 적용 완료. 구글 OAuth redirect URI는 `https://gamenuri.store/...`.
- 인증서 위치(proxy VM): 원본 `/etc/letsencrypt/live/gamenuri.store/`, HAProxy용 `/etc/haproxy/certs/gamenuri.store.pem`(fullchain+privkey, root:haproxy 640). 키 파일은 repo에 넣지 않는다.
- 갱신: `--manual` 방식이라 자동 갱신 안 됨. 만료 전에 `sudo certbot certonly --manual --preferred-challenges dns -d gamenuri.store`를 다시 실행하고 TXT 값을 가비아에 넣은 뒤, PEM을 다시 만들고 `systemctl reload haproxy`.
- 확인: 강의실 PC에서 `nslookup gamenuri.store`가 192.168.0.222를 돌려주는지 (학교·공유기 DNS의 rebinding 차단 여부).

## 호스트

| 호스트 이름 | IP | PC | 역할 | 주요 포트 |
|---|---|---|---|---|
| proxy | 10.0.1.1 (192.168.0.222) | PC-1 | 게이트웨이, HAProxy, 수집기 | 80·443(HAProxy), 8404(stats) |
| frontend1 | 10.0.1.101 | PC-1 | Frontend 1 | 80(nginx) |
| frontend2 | 10.0.1.102 | PC-1 | Frontend 2 | 80(nginx) |
| backend1 | 10.0.1.103 | PC-1 | Backend 1 | 8000(FastAPI) |
| backend2 | 10.0.1.104 | PC-1 | Backend 2 | 8000(FastAPI) |
| kafka1 | 10.0.1.105 | PC-1 | Kafka | 9092, 9093(controller), 8083(Connect) |
| kafka2 | 10.0.1.106 | PC-1 | Kafka | 9092, 9093, 8083 |
| kafka3 | 10.0.1.107 | PC-1 | Kafka | 9092, 9093, 8083 |
| backup | 10.0.1.108 | PC-1 | DB 백업 | 22 |
| monitoring | 10.0.2.1 (192.168.0.223) | PC-2 | 게이트웨이, Prometheus·Grafana | 9090, 3000 |
| mariadb-pr | 10.0.2.101 | PC-2 | MariaDB Primary (쓰기) | 3306 |
| mariadb-re | 10.0.2.102 | PC-2 | MariaDB Replica (읽기) | 3306 |
| elk | 10.0.2.103 | PC-2 | Elasticsearch·Kibana | 9200, 5601 |
| mongodb-pr | 10.0.2.104 | PC-2 | MongoDB Primary | 27017 |
| mongo-se1 | 10.0.2.105 | PC-2 | MongoDB Secondary 1 | 27017 |
| mongo-se2 | 10.0.2.106 | PC-2 | MongoDB Secondary 2 | 27017 |
| valkey | 10.0.2.107 | PC-2 | Valkey (캐시) | 6379 |

모든 VM 공통: 22(SSH), 9100(node_exporter)

## 계정
- 팀 계정: `admina`(김준영), `adminb`(남현식), `adminc`(이고은), `admind`(한예찬). 모두 `wheel`(sudo) + `gamenuri` 그룹.
- 공용 작업 폴더: `/opt/game-nuri` (root:gamenuri, 2775). 데이터 경로: `/DATA`.
- 기존 `admin` 계정은 비상용. 비밀번호는 문서·단톡방에 쓰지 않고 개인 메시지로 전달한다.

## 접속 (각자 PC)
`infra/ssh/config.example`을 `~/.ssh/config`에 붙여 넣는다. `10.0.1.*`는 proxy, `10.0.2.*`는 monitoring을 점프 서버로 거친다.

## 공유기 쪽에 여는 포트
- `192.168.0.222`(proxy): 22, 80, 443 만
- `192.168.0.223`(monitoring): 22, 3000(Grafana, 로그인 필수) 만
- DB·Kafka·Kibana 포트는 게이트웨이 바깥으로 열지 않는다.
