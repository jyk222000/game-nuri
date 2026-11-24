# 모니터링 (Prometheus · Alertmanager · Grafana · Loki)

실제 VM 출력으로 확인한 구성이다(2026-11-23~24, 남현식). **비밀번호와 Slack 웹훅 주소는 적지 않고 레포에도 없다**(4장).

서버는 `monitoring`(10.0.2.1, PC-2 게이트웨이)에 모여 있고, 나머지 VM에는 지표를 내보내는 exporter와 로그를 보내는 Alloy가 있다. 목적은 "수집되는 것이 Grafana에 보이고, 이상하면 Slack으로 알려 주는 것"이다.

## 1. 구성

| 구성요소 | 위치 | 버전 | 주소 | 메모리 상한 | 데이터 |
|---|---|---|---|---|---|
| Prometheus | monitoring | 3.13.3 LTS | `10.0.2.1:9090` | 350M | `/DATA/prometheus` (7일, 3GB) |
| Alertmanager | monitoring | 0.34.1 | `127.0.0.1:9095` | 100M | `/DATA/alertmanager` |
| Grafana | monitoring | 10.2.6 (OS 패키지) | `:3000` (로그인 필수) | 300M | `/var/lib/grafana` |
| Loki | monitoring | 3.7.7 | `10.0.2.1:3100` (gRPC 9096) | 550M | `/DATA/loki` (7일) |
| kafka_watch | monitoring | python3 (표준 라이브러리만) | `10.0.2.1:9399` | 250M | 없음 |
| Alloy (로그 수집) | mariadb-re, elk, kafka1~3, backend1·2 | 1.19.2 | 각 VM `:12345` | 350M | 없음 |
| node_exporter | 17대 | 1.13.1 | `:9100` | | |
| kafka_exporter | kafka1 | 1.11.0 | `:9308` | | |
| mysqld_exporter | mariadb-pr, mariadb-re | 0.21.0 | `:9104` | 100M | |
| mongodb_exporter | mongodb-pr, mongo-se1·2 | 0.53.0 | `:9216` | 100M | |
| Backend `/metrics` | backend1·2 | | `:8000` | | |

- 설정 파일의 IP(`10.0.2.1`)는 **서비스가 받는 주소(bind)** 와 Loki 주소다. 나머지 대상은 호스트 이름을 쓴다(`docs/network.md`).
- monitoring은 PC-2 게이트웨이다. iptables 규칙(FORWARD, MASQUERADE)을 건드리면 PC-2 전체가 끊긴다.
- monitoring은 Kafka KRaft 투표자 5번이기도 하다(`infra/kafka/README.md`). 서버 전체 재부팅은 투표 5대 중 1대가 빠지는 일이다.

## 2. 파일

| 파일 | 서버 위치 | 설명 |
|---|---|---|
| `prometheus.yml` | `/etc/prometheus/prometheus.yml` | 수집 대상(job)과 Alertmanager 연결 |
| `rules/kafka.rules.yml` | `/etc/prometheus/rules/` | Kafka 경보 9개 |
| `rules/monitoring.rules.yml` | 같음 | Kafka 직접 확인·로그 수집기·VM 기본 경보 12개 |
| `rules/db.rules.yml` | 같음 | MariaDB·MongoDB 경보 9개 |
| `alertmanager/alertmanager.yml` | `/etc/alertmanager/alertmanager.yml` | Slack 알림 형식과 재전송 간격 |
| `systemd/prometheus.service`, `alertmanager.service`, `loki.service`, `kafka-watch.service` | `/etc/systemd/system/` | |
| `systemd/grafana-server.override.conf` | `/etc/systemd/system/grafana-server.service.d/override.conf` | 로그인 필수·가입 차단·메모리 상한 |
| `grafana/provisioning/datasources/*.yml` | `/etc/grafana/provisioning/datasources/` | Prometheus(기본), Loki |
| `grafana/provisioning/dashboards/gamenuri.yml` | `/etc/grafana/provisioning/dashboards/` | 폴더 `겜누리`, 화면에서 저장 불가, 30초마다 파일 확인 |
| `grafana/dashboards/*.json` | `/etc/grafana/dashboards/` | 대시보드 4개 (5장) |
| `loki/loki.yaml` | `/etc/loki/loki.yaml` | 보관 7일, 파일 저장소 |
| `kafka-watch/kafka_watch.py` | `/opt/kafka-watch/kafka_watch.py` | 3장 |
| `scripts/alloy-setup.sh` | 각 VM `~` | Alloy 설치·설정 |
| `scripts/exporter-setup.sh` | DB VM `~` | mysqld_exporter·mongodb_exporter 설치 |
| `node-exporter.service` | `/etc/systemd/system/` (모든 VM) | monitoring은 `--web.listen-address=10.0.2.1:9100` |

`/etc/prometheus`, `/etc/alertmanager`, `/etc/grafana`는 서비스 계정 전용이라 adminb가 직접 읽지 못한다. 확인·검사는 `sudo`로 한다.

## 3. 수집 대상 (job)

| job | 대상 | 비고 |
|---|---|---|
| node | 17대 `:9100` | 호스트 이름 |
| kafka | `kafka1:9308` | kafka_exporter |
| mariadb | `mariadb-pr:9104`, `mariadb-re:9104` | mysqld_exporter |
| mongodb | `mongodb-pr:9216`, `mongo-se1:9216`, `mongo-se2:9216` | mongodb_exporter (복제 셋 3대 모두) |
| backend | `backend1:8000`, `backend2:8000` | FastAPI `/metrics` (Backend의 API 사용 순위도 이 지표를 쓴다) |
| kafka_watch | `10.0.2.1:9399` | 5초마다 수집 |
| loki | `10.0.2.1:3100` | |
| alloy | 위 표의 7대 `:12345` | |

**kafka_watch**: Prometheus는 15초마다 가져가서 짧게 꺼졌다 켜지는 롤링 재시작을 놓친다. 그래서 monitoring에서 브로커(9092)·컨트롤러(9093) 8곳에 **2초마다 직접 접속**하고, 2번 연속 실패하면 "꺼짐"으로 센다(꺼짐 횟수·시간도 지표). 30초마다 `kafka-metadata-quorum.sh describe`로 컨트롤러 리더와 정족수를 읽는다. 실행 계정 `kafkawatch`.

**경보 규칙 30개** (`severity: critical`은 Slack 1시간마다, `warning`은 4시간마다 다시 알린다. 복구 알림도 간다.)
- `kafka.rules.yml` 9: 브로커 감소, 복제 부족, 쓰기 막힘, exporter·서비스 중단, 디스크, 소비 지연, Connect 작업 실패·상태 갱신 멈춤
- `monitoring.rules.yml` 12: KafkaBrokerUnreachable, KafkaControllerUnreachable, KafkaControllerQuorumLost(접속 컨트롤러 3대 미만), KafkaControllerLeaderChanged, KafkaWatchBlind, AlloyDown, LokiDown, VMDown, BackendDown, HostMemoryLow, HostDiskLowOthers, HostCpuHigh
- `db.rules.yml` 9: MariaDBDown·ReplicationBroken·ReplicationLag·ConnectionsHigh·SlowQueries, MongoDBDown·NoPrimary·MemberUnhealthy·ReplicationLag
- BackendDown은 **최근 하루 안에 한 번이라도 정상이던 서버만** 본다(배포 전 서버는 제외).
- 계획된 Kafka 재시작 때는 브로커·컨트롤러 경보가 온다. 정상이다.

## 4. 레포에 없는 것 (서버에만 있다)

| 항목 | 서버 위치 | 어떻게 정했나 |
|---|---|---|
| Slack 웹훅 주소 | `/etc/alertmanager/slack_webhook` (alertmanager 소유, 600) | 팀에서 받아 `read -rs`로 입력. 설정에서는 `api_url_file`로 읽음 |
| Grafana 관리자 비밀번호 | Grafana DB (`/var/lib/grafana`) | `grafana-cli admin reset-admin-password`로 설정, 담당자가 비밀번호 관리 도구에 보관 |
| DB exporter 비밀번호 | `/etc/mysqld_exporter.cnf` (600), `/etc/mongodb_exporter.env` (600, root) | `exporter-setup.sh`가 입력을 받아 저장 |

DB에는 **읽기 전용 계정 `exporter`** 를 만들었다(비밀번호는 새로 정한 값). MariaDB는 mariadb-pr에서 한 번 만들면 복제로 mariadb-re에도 생긴다.

```sql
-- mariadb-pr (root로). <비밀번호> 자리는 직접 입력
CREATE USER 'exporter'@'localhost' IDENTIFIED BY '<비밀번호>' WITH MAX_USER_CONNECTIONS 3;
GRANT PROCESS, BINLOG MONITOR, REPLICA MONITOR, SELECT ON *.* TO 'exporter'@'localhost';
```

```js
// mongodb-pr (PRIMARY, admin으로). 비밀번호는 입력창에 직접 입력
db.getSiblingDB("admin").createUser({ user: "exporter", pwd: passwordPrompt(),
  roles: [{ role: "clusterMonitor", db: "admin" }, { role: "read", db: "local" }] })
```

## 5. 대시보드 4개 (서로 이동하는 링크가 걸려 있다)

| uid | 제목 | 내용 |
|---|---|---|
| gamenuri-overview | 겜누리 종합 | 상태 한눈에, API 트래픽·사용 순위, Kafka, 서버 자원 |
| gamenuri-kafka | 겜누리 Kafka 상세 | 브로커·컨트롤러 5대(투표) 상태와 리더, 재시작 감지, 복제·소비 지연, Connect, 클릭스트림 |
| gamenuri-logs | 겜누리 로그 | VM·서비스 선택, 에러 징후, 에러/전체 로그, Alloy·Loki 상태 |
| gamenuri-db | 겜누리 DB | MariaDB 원본·복제본·복제 상태·지연, MongoDB 3대 역할, 부하, DB VM 디스크 |

파일 하나가 대시보드 하나다. 지우거나 합치려면 파일을 옮기면 된다(30초 안에 반영). 데이터 소스는 숨은 변수 `ds`로 받아서 같은 JSON이 다른 Grafana에서도 동작한다.

## 6. 설치 순서 (monitoring, 요약)

1. **Prometheus**: 공식 릴리스를 받아 `sha256sum` 확인 후 `install -m 0755`로 `/usr/local/bin`. 계정 `prometheus`(nologin), 데이터 `/DATA/prometheus`. `prometheus.yml`·`rules/`를 `/etc/prometheus/`에 `install`, 서비스 등록. 반영 전에 `sudo -u prometheus /usr/local/bin/promtool check config /etc/prometheus/prometheus.yml`.
2. **Alertmanager**: 같은 방식. 계정 `alertmanager`, 데이터 `/DATA/alertmanager`. `slack_webhook` 파일은 600으로 만들고 값은 입력받는다. 확인은 `amtool check-config`.
3. **Grafana**: OS 패키지 10.2.6을 쓴다. 서비스 drop-in, provisioning 2종, 대시보드 JSON을 배치한다.
4. **Loki**: 공식 릴리스, 계정 `loki`, 데이터 `/DATA/loki`. gRPC 기본 포트 9095가 Alertmanager와 겹쳐 9096으로 바꿨다.
5. **kafka_watch**: 계정 `kafkawatch`, `/opt/kafka-watch/`, `/opt/kafka/bin/kafka-metadata-quorum.sh`를 읽을 수 있어야 한다.
6. **Alloy**: `scripts/alloy-setup.sh`. 디스크 여유가 설치 후 17% 미만이면 멈춘다. 사용: `EXTRA_GROUPS="mysql" FILES="서비스=경로 ..." bash alloy-setup.sh`
7. **DB exporter**: DB 읽기 전용 계정 생성(4장) 후 `scripts/exporter-setup.sh mysql|mongo`. 전용 계정 `dbexporter`, 체크섬 검증, monitoring에서 오는 접속만 허용(firewalld가 켜져 있을 때).

설정을 바꾼 뒤 반영: `sudo systemctl kill -s HUP prometheus` (수집 설정·규칙), `sudo systemctl restart grafana-server` (provisioning을 바꿨을 때만, 대시보드 JSON은 자동).

**로그 라벨**: `host`(VM 이름), `service`(서비스 이름), `level`(journald 우선순위, 파일 로그에는 없음).

## 7. 알려진 한계·남은 일

- 로그는 7대만 모은다. proxy(RAM 595MB), mongodb-pr(RAM 660MB), mariadb-pr(디스크)는 Alloy가 부담이라 뺐다. 나머지 VM은 필요할 때 추가한다.
- `backend2:8000`은 Backend 배포 전이라 down으로 보인다(BackendDown 경보에서는 제외).
- HAProxy(`proxy:8404`) 지표는 HAProxy 쪽에서 지표 포트를 켠 뒤 job을 추가한다.
- Locust 부하 시험과 장애 시연(Slack까지 경보가 오는지)은 아직 하지 않았다.
- node_exporter의 systemd 필터는 Kafka·DB 등 서비스 이름만 본다. Backend 서비스(`backend.service`)는 넣지 않았다(`BackendDown`이 같은 일을 한다).
