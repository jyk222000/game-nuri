# Kafka 클러스터 · Kafka Connect

실제 VM 출력으로 확인한 구성이다(2026-11-21). 비밀번호는 적지 않는다.

## 1. 구성

| VM | node.id | 역할 | 힙 | 포트 | 데이터 · 로그 |
|---|---|---|---|---|---|
| kafka1 | 1 | 브로커 + 투표자, Connect, kafka_exporter | Kafka 1G, Connect 512M | 9092, 9093, 8083, 9308, 9100 | `/DATA/kafka`, `/DATA/kafka-applog`, `/DATA/connect-applog` |
| kafka2 | 2 | 브로커 + 투표자, Connect | 같음 | 9092, 9093, 8083, 9100 | 같음 |
| kafka3 | 3 | 브로커 + 투표자, Connect | 같음 | 9092, 9093, 8083, 9100 | 같음 |
| backup | 4 | 투표자만 | 192M | 9093, 9100 | `/var/lib/kafka-meta`, `/var/log/kafka` |
| monitoring | 5 | 투표자만 | 256M | 9093, 9100 (둘 다 10.0.2.1에만) | `/DATA/kafka-meta`, `/DATA/kafka-applog` |

- Kafka 3.8.0 (Scala 2.13, `/opt/kafka` → `/opt/kafka_2.13-3.8.0`), Java 21 (`java-21-openjdk-headless`), 실행 계정 `kafka`
- 클러스터 ID `5CwAAL18QCS90wZSozhe7w`
- **투표자 5대**: 어느 브로커 2대가 죽어도 투표 과반(3/5)이 남아, 운영자가 설정을 바꿔 남은 1대로 운영할 수 있다(6장). Kafka 3.8은 투표자 목록을 나중에 바꾸려면 재포맷해야 해서 처음부터 5대로 정했다.
- 토픽은 `create-topics.sh`로 만든다. 파티션 3, 복제 3, `min.insync.replicas=2`(브로커 기본값). 자동 생성은 끈다.

## 2. 파일

| 파일 | 서버 위치 | 대상 |
|---|---|---|
| `server.properties.broker.example` | `/etc/kafka/server.properties` | kafka1~3 |
| `server.properties.controller.example` | `/etc/kafka/server.properties` | backup, monitoring |
| `connect-distributed.properties.example` | `/etc/kafka/connect-distributed.properties` | kafka1~3 |
| `systemd/kafka.service` | `/etc/systemd/system/` | 5대 (힙·로그 폴더만 다름) |
| `systemd/kafka-connect.service` | 같음 | kafka1~3 |
| `systemd/kafka-log-cleanup.service`, `.timer` | 같음 | 5대 (로그 폴더만 다름) |
| `systemd/kafka-exporter.service` | 같음 | kafka1 |
| `systemd/refiner.service`, `refiner.env.example` | 같음, `/etc/game-nuri/refiner.env` | kafka1~3 (코드 전까지 enable 안 함) |
| `../monitoring/node-exporter.service` | 같음 | 모든 VM |
| `create-topics.sh` | – | kafka1에서 한 번 |
| `connect-status-exporter.sh`, `systemd/connect-status-exporter.service`·`.timer` | `/usr/local/bin/`, `/etc/systemd/system/` | kafka1 (Connect 작업 상태 → node_exporter textfile) |
| `../monitoring/rules/kafka.rules.yml` | Prometheus `rules/` | monitoring (경보 규칙 9개) |

## 3. 설치 순서 (Rocky Linux 10)

MobaXterm MultiExec으로 여러 대에 같은 명령을 넣을 때는 Exclude를 먼저 확인한다. VM마다 다른 값은 `export`로 넣고 명령은 변수를 쓴다.

1. **사전 확인** `hostname`, `df -h / /DATA`, `free -h`, `getent hosts kafka1 kafka2 kafka3 backup monitoring`
2. **GUI 끄기** `sudo systemctl set-default multi-user.target && sudo systemctl isolate multi-user.target`
3. **Java** `sudo dnf install -y java-21-openjdk-headless`
4. **Kafka** kafka1에서만 받고 나머지는 `scp`로 복사한다. archive.apache.org는 연속 다운로드를 크게 제한한다(45분). `sha512sum`으로 같은 파일인지 확인한다.
   ```bash
   curl -fLO https://archive.apache.org/dist/kafka/3.8.0/kafka_2.13-3.8.0.tgz   # kafka1
   sudo tar -xzf kafka_2.13-3.8.0.tgz -C /opt && sudo ln -sfn /opt/kafka_2.13-3.8.0 /opt/kafka
   sudo useradd -r -M -d /opt/kafka -s /sbin/nologin kafka
   sudo mkdir -p /DATA/kafka /DATA/kafka-applog /etc/kafka            # 폴더는 1장 표 기준
   sudo chown -R kafka:kafka /opt/kafka_2.13-3.8.0 /DATA/kafka /DATA/kafka-applog /etc/kafka
   echo 'export PATH=$PATH:/opt/kafka/bin' | sudo tee /etc/profile.d/kafka.sh
   ```
5. **설정** 예시 파일의 `${ID}`, `${NAME}`, `${META}`를 채워 `/etc/kafka/server.properties`에 둔다(`chown kafka:kafka`).
6. **포맷** 클러스터 ID는 한 대에서 **한 번만** 만들고 5대가 같은 값을 쓴다. 포맷은 처음 한 번만 한다.
   ```bash
   kafka-storage.sh random-uuid                                         # 한 대에서 한 번
   sudo -u kafka /opt/kafka/bin/kafka-storage.sh format -t "$CID" -c /etc/kafka/server.properties   # 5대
   ```
7. **방화벽** kafka1~3·backup은 firewalld가 켜져 있다(`docs/network.md`와 다름). monitoring은 게이트웨이라 손대지 않는다.
   ```bash
   sudo firewall-cmd --permanent --add-port=9092/tcp --add-port=9093/tcp --add-port=8083/tcp --add-port=9100/tcp   # kafka1~3
   sudo firewall-cmd --permanent --add-port=9308/tcp                                                                # kafka1
   sudo firewall-cmd --permanent --add-port=9093/tcp --add-port=9100/tcp                                            # backup
   sudo firewall-cmd --reload
   ```
8. **기동** 5대 **동시에** 켠다. 과반(3대)이 모여야 리더가 뽑힌다.
   ```bash
   sudo systemctl daemon-reload && sudo systemctl enable --now kafka
   kafka-metadata-quorum.sh --bootstrap-server kafka1:9092 describe --status       # CurrentVoters [1,2,3,4,5]
   kafka-metadata-quorum.sh --bootstrap-server kafka1:9092 describe --replication  # 5대 Lag 0
   ```
9. **토픽** kafka1에서 `bash infra/kafka/create-topics.sh`
10. **Connect** (kafka1~3) 설정·서비스 파일 배치 → `enable --now kafka-connect` → `curl kafka1:8083/connector-plugins`
11. **플러그인** kafka1에서 받아 `/opt/kafka-plugins`에 풀고 `tar`로 묶어 kafka2·3에 복사 → Connect 재시작

| 플러그인 | 버전 | 받는 곳 | 위치 |
|---|---|---|---|
| Confluent JDBC | 10.9.10 | `api.hub.confluent.io` (archive URL) | `/opt/kafka-plugins/confluentinc-kafka-connect-jdbc-10.9.10/` |
| MariaDB 드라이버 | 3.5.11 | Maven Central `org.mariadb.jdbc:mariadb-java-client` | 위 JDBC 폴더의 `lib/` |
| MongoDB connector | 3.1.3 (`-all.jar`) | Maven Central `org.mongodb.kafka:mongo-kafka-connect` | `/opt/kafka-plugins/mongo-kafka-connect/` |
| File connector (시험용) | 3.8.0 | `/opt/kafka/libs/connect-file-3.8.0.jar` | `/opt/kafka-plugins/file-connector/` |
| Elasticsearch | 미정 | ES 버전이 정해진 뒤 | – |

12. **운영 도구** 로그 정리 타이머(5대), kafka_exporter(kafka1), node_exporter(5대), refiner 환경(kafka1~3: `/opt/game-nuri/repo/.venv`, `pip install -r pipeline/requirements.txt -e shared`)

바이너리를 `/tmp`에서 옮길 때는 `mv`가 아니라 `install -m 0755`를 쓴다. SELinux가 Enforcing이라 `mv`하면 임시 파일 레이블이 남아 실행이 막힐 수 있다.

## 4. 확인

```bash
kafka-topics.sh --bootstrap-server kafka1:9092 --describe --topic raw.price   # 리더가 1·2·3에 흩어지고 Isr 3개
curl -s http://kafka1:8083/connectors                                          # 등록된 커넥터
curl -s http://kafka1:9308/metrics | grep '^kafka_brokers '                    # 3
curl -s http://kafka1:9100/metrics | grep 'node_systemd_unit_state{name="kafka.service",state="active"'
```

시험 메시지는 `test.smoke`(보관 1시간)에만 넣는다. 실제 토픽에 넣으면 Connect와 refiner가 처음부터 읽어 DB에 들어간다.

## 5. 지킬 것

- 토픽 삭제, offset 초기화, 재포맷은 팀장 확인 후.
- 점검은 한 대씩. 다음 대는 앞 대의 `Isr`이 3개로 돌아온 뒤에 끈다.
- 5대의 Kafka 버전과 `controller.quorum.voters`를 같게 유지한다.
- Connect 설정은 `pipeline/connect/*.json` + `apply.sh`로만 바꾼다.

- JMX는 쓰지 않는다. `kafka-run-class.sh`는 `KAFKA_JMX_OPTS`가 비어 있으면 인증 없는 JMX를 켜고 `0.0.0.0`의 임의 포트를 연다(11/23 확인: 5대 모두). 서비스 파일에서 `KAFKA_JMX_OPTS`를 채워 막는다. 지표는 kafka_exporter와 Connect 상태 스크립트로 모은다.

## 6. 장애 시험 결과 (11/20~21)

| 시나리오 | 결과 |
|---|---|
| 브로커 1대 중단 | 리더·투표 리더가 자동으로 넘어가고 쓰기·읽기 계속. 복구 후 `Isr` 3개, 약 5분 뒤 리더도 원래 자리 |
| 브로커 2대 중단 | 투표 과반(1·4·5) 유지, 쓰기는 `NOT_ENOUGH_REPLICAS`로 거부 (데이터 보호) |
| 2대 중단 중 1대 운영 | 아래 명령으로 `min.insync.replicas`를 1로 낮추면 kafka1 혼자 처리. 복구 후 되돌림 |
| Connect 1대 중단 | 작업이 다른 작업자로 넘어가 이어서 처리 |

```bash
# 2대 장애 때만. 복구해서 Isr이 3개로 돌아오면 반드시 되돌린다
kafka-configs.sh --bootstrap-server kafka1:9092 --alter --entity-type brokers --entity-default --add-config min.insync.replicas=1
kafka-configs.sh --bootstrap-server kafka1:9092 --alter --entity-type brokers --entity-default --delete-config min.insync.replicas
```

## 7. 겪은 문제

| 문제 | 원인 | 해결 |
|---|---|---|
| 브로커끼리 `No route to host` | firewalld가 켜져 있었다 | 7단계 포트 열기 |
| 자기 호스트 이름이 `fe80::`로 해석 | IPv6 링크 로컬이 먼저 나옴 | `-Djava.net.preferIPv4Stack=true` |
| 다운로드 45분 예상 | archive.apache.org 연속 다운로드 제한 | kafka1에서 `scp` 복사 |
| 덜 받은 파일로 압축이 풀림 | 여러 줄 붙여 넣기 중 `Ctrl+C`는 다운로드만 멈춤 | 같은 위치에 다시 풀어 덮어씀. 중요한 단계는 `&&`로 연결 |
| `systemctl stop` 후 `failed` | Java 종료 코드 143 | `SuccessExitStatus=143` |
| 2대 장애 때 메시지가 버려짐 | 콘솔 producer 재시도 3번 | 수집기는 `delivery.timeout.ms`를 넉넉히 |
| 거부 뒤 `OUT_OF_ORDER_SEQUENCE_NUMBER` | 실패로 producer 순번이 비었다 | producer를 새로 만든다 |
