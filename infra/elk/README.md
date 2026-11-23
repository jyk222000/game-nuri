# elk (Elasticsearch · Kibana)

설치 순서, 설정 파일 위치, 확인 명령을 기록한다. 비밀번호는 쓰지 않는다. 설치 2026-11-23, 남현식.
Monstache는 `infra/monstache/README.md`.

## 1. 구성

| 항목 | 값 |
|---|---|
| VM | `elk` 10.0.2.103, RAM 5.5Gi, vCPU 2, `/` 15G, `/DATA` 20G, Rocky 10 (커널 6.12.0-264), SELinux Enforcing |
| 부팅 모드 | `multi-user.target` (GUI 끔, 사용 메모리 975Mi → 698Mi) |
| Elasticsearch | **8.19.25** (공식 RPM 저장소, `enabled=0`), 클러스터 `gamenuri`, 노드 1대 |
| 플러그인 | `analysis-nori` 8.19.25 |
| 힙 | 2GB (`/etc/elasticsearch/jvm.options.d/heap.options`) |
| 데이터 · 로그 | `/DATA/elasticsearch` (elasticsearch 2750) · `/var/log/elasticsearch/gamenuri.log` |
| 보안 | 로그인 켬(`xpack.security.enabled`), **HTTP TLS 끔** (`http://elk:9200`), 노드 간 TLS는 자동 설정 그대로 |
| 접속 범위 | `network.host: ["_local_", "_site_"]` (localhost + 10.0.2.103) |
| 계정 | `elastic`(관리자, 프로그램도 이 계정), `kibana_system`(Kibana 전용, 키스토어에만) — `docs/decisions.md` 11/23 |
| Kibana | **8.19.25**, `server.host: "elk"`, 포트 5601, Node 힙 1GB (`/etc/kibana/node.options`) |
| node_exporter | 1.13.1, 포트 9100, 서비스 `node-exporter` (6장) |

## 2. 설치 순서 (elk, adminb)

`/etc/elasticsearch`, `/etc/kibana`는 adminb가 `cd`할 수 없다. 명령에 전체 경로를 쓴다.

```bash
# 저장소 (평소 dnf update에 섞이지 않게 enabled=0)
sudo rpm --import https://artifacts.elastic.co/GPG-KEY-elasticsearch
sudo tee /etc/yum.repos.d/elasticsearch.repo >/dev/null <<'EOF'
[elasticsearch]
name=Elasticsearch repository for 8.x packages
baseurl=https://artifacts.elastic.co/packages/8.x/yum
gpgcheck=1
gpgkey=https://artifacts.elastic.co/GPG-KEY-elasticsearch
enabled=0
autorefresh=1
type=rpm-md
EOF

# ES (설치 출력의 자동 생성 비밀번호는 화면에서 거른다. 아래에서 새로 정함)
sudo dnf install -y --enablerepo=elasticsearch 'elasticsearch-8.19.*' 2>&1 | grep -v -i password
sudo /usr/share/elasticsearch/bin/elasticsearch-plugin install --batch analysis-nori

# elasticsearch.yml: 데이터 경로, 접속 범위, HTTP TLS 끄기, 클러스터 이름 (원본은 .orig)
F=/etc/elasticsearch/elasticsearch.yml
sudo cp -a $F $F.orig
sudo sed -i \
  -e 's|^path.data: /var/lib/elasticsearch|path.data: /DATA/elasticsearch|' \
  -e 's|^http.host: 0.0.0.0|network.host: ["_local_", "_site_"]|' \
  -e '/^xpack.security.http.ssl:/,/^xpack.security.transport.ssl:/ s/enabled: true/enabled: false/' $F
echo 'cluster.name: gamenuri' | sudo tee -a $F >/dev/null

# 힙, 데이터 폴더
printf -- '-Xms2g\n-Xmx2g\n' | sudo tee /etc/elasticsearch/jvm.options.d/heap.options >/dev/null
sudo chown root:elasticsearch /etc/elasticsearch/jvm.options.d/heap.options
sudo chmod 660 /etc/elasticsearch/jvm.options.d/heap.options
sudo install -d -o elasticsearch -g elasticsearch -m 2750 /DATA/elasticsearch
sudo systemctl daemon-reload && sudo systemctl enable --now elasticsearch

# 비밀번호는 -i 프롬프트로만 입력
sudo /usr/share/elasticsearch/bin/elasticsearch-reset-password -u elastic -i
sudo /usr/share/elasticsearch/bin/elasticsearch-reset-password -u kibana_system -i

# Kibana (kibana_system 비밀번호는 kibana.yml이 아니라 키스토어에)
sudo dnf install -y --enablerepo=elasticsearch kibana-8.19.25
sudo /usr/share/kibana/bin/kibana-keystore add elasticsearch.password
sudo chown root:kibana /etc/kibana/kibana.keystore && sudo chmod 660 /etc/kibana/kibana.keystore
K=/etc/kibana/kibana.yml; sudo cp -a $K $K.orig
sudo tee -a $K >/dev/null <<'EOF'

# --- gamenuri ---
server.host: "elk"
elasticsearch.hosts: ["http://elk:9200"]
elasticsearch.username: "kibana_system"
EOF
echo '--max-old-space-size=1024' | sudo tee -a /etc/kibana/node.options >/dev/null
sudo systemctl enable --now kibana
```

## 3. 인덱스 · 템플릿

| 이름 | 파일 | 넣는 쪽 |
|---|---|---|
| `games`, `reviews` | `infra/monstache/*-index.json` | Monstache |
| `clickstream-*` (템플릿 `clickstream`) | `clickstream-template.json` | Kafka Connect `es-sink-clickstream` (날짜별 `clickstream-YYYY.MM.dd`) |

```bash
curl -s -u elastic -X PUT http://elk:9200/_index_template/clickstream \
  -H 'Content-Type: application/json' --data-binary @infra/elk/clickstream-template.json
```
자동 인덱스 생성은 막지 않았다. 매핑 파일로 인덱스를 먼저 만들고 Monstache를 켠다(순서 지키기).

## 4. 확인
```bash
curl -s -u elastic 'http://elk:9200/?pretty'                      # 8.19.25, cluster_name gamenuri
curl -s -u elastic 'http://elk:9200/_cluster/health?pretty'       # green
curl -s -u elastic 'http://elk:9200/_cat/plugins?v'               # analysis-nori
curl -s -u elastic 'http://elk:9200/_cat/indices?v'
curl -s -o /dev/null -w '%{http_code}\n' http://elk:9200          # 다른 VM에서: 401이면 연결 정상
```
nori 확인: `POST games/_analyze {"analyzer":"korean","text":"엘든링을 샀다"}` → `엘든`, `링`, …

## 5. Kibana 접속 (SSH 터널)

elk는 내부망이라 PC 브라우저에서 바로 열 수 없다. PC-2 게이트웨이(monitoring 192.168.0.223)를 거친다.
- MobaXterm **Tunneling** → New SSH tunnel → Local port forwarding:
  Forwarded port `5601`, SSH server `192.168.0.223` / 자기 계정 / `22`, Remote server `elk` / `5601`
- 또는 PC 터미널: `ssh -N -L 5601:elk:5601 <계정>@192.168.0.223`
- 브라우저 `http://localhost:5601` → `elastic` 로그인

데이터가 들어오면 Data View를 만든다: `clickstream-*` (시간 필드 `occurred_at`), `games`, `reviews`.

## 6. node_exporter (모니터링)

`infra/monitoring/node-exporter.service`와 같은 방식(1.13.1, 계정 `node_exporter`, 포트 9100). elk만 감시 서비스를 바꿨다.
```
--collector.systemd.unit-include=(elasticsearch|kibana|monstache)\.service
```
설치 11/24. 확인: `curl -s localhost:9100/metrics | grep '^node_systemd_unit_state{.*state="active"'` → 세 서비스 값 1,
monitoring에서 `curl -s http://elk:9100/metrics | grep -c '^node_'` (534). Prometheus `prometheus.yml`의 `elk:9100`으로 수집된다.

## 7. 계정 비밀번호를 바꿀 때
`elastic` 비밀번호를 바꾸면 함께 바꾼다: kafka1 `/opt/game-nuri/repo/.env`(`ES_PASSWORD`) 후 `apply.sh es-sink-clickstream`,
elk `/etc/monstache/monstache.env` 후 `systemctl restart monstache`, backend `.env`(Backend가 ES를 쓸 때).
