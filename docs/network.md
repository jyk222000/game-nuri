# 네트워크 · 호스트 · 포트

> 코드에는 IP를 쓰지 않는다. 각 VM의 `/etc/hosts`(= `infra/hosts`)에 아래 호스트 이름을 등록한다.
> 구축 방법은 `docs/infra-workbook.md`. 공유기망 게이트웨이 `192.168.0.1`은 가정값 — 실제 값으로 확인할 것.

## 대역
| 망 | 대역 | 게이트웨이 | VirtualBox |
|---|---|---|---|
| 공유기망 (0번대) | 192.168.0.0/24 | 192.168.0.1 | 브리지 — proxy, monitor만 |
| PC-1 내부망 | 10.0.1.0/24 | proxy `10.0.1.1` | 내부 네트워크 `pc1-net` |
| PC-2 내부망 | 10.0.2.0/24 | monitor `10.0.2.1` | 내부 네트워크 `pc2-net` |

- 두 내부망 사이: proxy ↔ monitor가 서로의 내부망으로 라우팅 (proxy: `10.0.2.0/24 via 192.168.0.223`, monitor: `10.0.1.0/24 via 192.168.0.222`)
- 인터넷: 각 게이트웨이가 NAT. 내부망 사이 통신에는 NAT를 걸지 않는다.

## VM 표 (OS: Rocky Linux 10)
| 호스트 이름 | 내부 IP | 공유기망 IP | PC | RAM / vCPU / Disk | 주요 포트 · 비고 |
|---|---|---|---|---|---|
| proxy | 10.0.1.1 | 192.168.0.222 | PC-1 | 2GB / 2 / 20GB | 80·443(HAProxy), 8404(stats), **PC-1 게이트웨이(NAT·라우팅)** |
| fe1 | 10.0.1.11 | – | PC-1 | 2GB / 1 / 20GB | 80(nginx) |
| fe2 | 10.0.1.12 | – | PC-1 | 2GB / 1 / 20GB | 80(nginx) |
| be1 | 10.0.1.21 | – | PC-1 | 2GB / 2 / 20GB | 8000(FastAPI) |
| be2 | 10.0.1.22 | – | PC-1 | 2GB / 2 / 20GB | 8000(FastAPI) |
| kafka1 | 10.0.1.31 | – | PC-1 | 4GB / 2 / 30GB | 9092, 9093(controller), 8083(Connect), 데이터 `/DATA` |
| kafka2 | 10.0.1.32 | – | PC-1 | 4GB / 2 / 30GB | 9092, 9093, 8083 |
| kafka3 | 10.0.1.33 | – | PC-1 | 4GB / 2 / 30GB | 9092, 9093, 8083 |
| backup | 10.0.1.40 | – | PC-1 | 1GB / 1 / 100GB | 22, 백업 `/BACKUP` |
| monitor | 10.0.2.1 | 192.168.0.223 | PC-2 | 2GB / 1 / 30GB | 9090(Prometheus), 3000(Grafana), 22(점프), **PC-2 게이트웨이(NAT·라우팅)** |
| mariadb-p | 10.0.2.51 | – | PC-2 | 3GB / 2 / 30GB | 3306, 데이터 `/DATA/mysql` |
| mariadb-r | 10.0.2.52 | – | PC-2 | 3GB / 2 / 30GB | 3306, 데이터 `/DATA/mysql` |
| mongo1 | 10.0.2.61 | – | PC-2 | 2GB / 2 / 30GB | 27017, 데이터 `/DATA/mongodb` |
| mongo2 | 10.0.2.62 | – | PC-2 | 2GB / 1 / 30GB | 27017 |
| mongo3 | 10.0.2.63 | – | PC-2 | 2GB / 1 / 30GB | 27017 |
| elk | 10.0.2.71 | – | PC-2 | 6GB / 2 / 40GB | 9200(ES), 5601(Kibana), 데이터 `/DATA` |
| valkey | 10.0.2.81 | – | PC-2 | 1GB / 1 / 10GB | 6379 |

모든 VM 공통: 22(SSH), 9100(node_exporter). 메모리 합계 PC-1 23GB, PC-2 21GB.

## 외부에 여는 포트 (공유기망 IP)
- `192.168.0.222` (proxy): 80, 443, SSH
- `192.168.0.223` (monitor): 3000(Grafana, 로그인 필수), SSH
- DB·Kafka·Kibana 포트는 **절대** 공유기망 쪽으로 열지 않는다.
