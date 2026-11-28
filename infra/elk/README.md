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
| `clickstream-*` (템플릿 `clickstream`) | `clickstream-template.json` | Kafka Connect `es-sink-clickstream` (날짜별 `clickstream-YYYY.MM.dd`). 들어올 때 파이프라인 `clickstream-game-name`이 `game_name`·`user_name`을 붙인다 (8장) |
| `users` | `users-index.json` | `es-users-sync` 타이머 (8장). 사용자 번호와 표시 이름만 |

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

## 5. Kibana 접속

**강의실 LAN (11/26~, 11/29부터 HTTPS)**: 브라우저 `https://gamenuri.store:5601` → `elastic` 로그인 → 첫 화면이 대시보드 "겜누리 사용자 행동 (clickstream)". **도메인으로 접속한다**(IP `192.168.0.222`로 들어가면 인증서가 도메인용이라 경고가 난다). `https://`를 붙여야 한다(`host:5601`만 치면 브라우저가 http로 시도해 실패).
proxy의 HAProxy가 5601을 `elk:5601`로 넘긴다 (`infra/haproxy/haproxy.cfg`의 `frontend kibana`, 팀장 확인).
- proxy SELinux: `sudo semanage port -a -t http_port_t -p tcp 5601` (Enforcing이라 HAProxy가 5601을 쓰려면 필요)
- 11/29부터 HAProxy가 5601에서 TLS를 종단한다(`bind *:5601 ssl crt /etc/haproxy/certs/gamenuri.store.pem`, 443과 같은 인증서). 이전에는 http라 로그인 비밀번호가 LAN에 암호화 없이 지나갔다. 발표 뒤 닫을 때: proxy에서 `haproxy.cfg`의 kibana 두 블록을 지우고 `haproxy -c -f /etc/haproxy/haproxy.cfg && systemctl reload haproxy`
- 첫 화면: Stack Management → Advanced Settings → `defaultRoute` = `/app/dashboards#/view/f8a35db7-9dae-4ce9-b98c-24495bcf6ead?_g=(filters:!(),refreshInterval:(pause:!f,value:10000),time:(from:now-7d,to:now))`
  (`http://…`를 앞에 붙이면 저장되지 않는다. `/app/`부터)

**SSH 터널 (관리용)**

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

## 8. clickstream에 게임 이름·사용자 이름 붙이기 (11/26)

Kibana에서 `game_id`, `user_id` 숫자 대신 이름으로 보려고 ES enrich를 쓴다. 기록이 **들어올 때** 붙이므로 지난 기록은 `_update_by_query`로 한 번 다시 처리한다.

```
MariaDB users ──(es-users-sync, 1분)──▶ ES users ──enrich 정책 users-name──┐
MongoDB games ──(Monstache)───────────▶ ES games ──enrich 정책 games-name──┤
Kafka clickstream ──(es-sink-clickstream)──▶ 파이프라인 clickstream-game-name ──▶ clickstream-YYYY.MM.dd (game_name, user_name)
```

### 만들기 순서 (Dev Tools)
1. `PUT users` ← `users-index.json`
2. elk에 동기화 스크립트·타이머 (아래) → `es-users-sync --no-enrich` 한 번
3. enrich 정책 두 개를 만들고 실행
   ```
   PUT _enrich/policy/games-name
   { "match": { "indices": "games", "match_field": "game_id", "enrich_fields": ["name", "name_ko"] } }
   POST _enrich/policy/games-name/_execute?wait_for_completion=true
   PUT _enrich/policy/users-name
   { "match": { "indices": "users", "match_field": "user_id", "enrich_fields": ["display_name"] } }
   POST _enrich/policy/users-name/_execute?wait_for_completion=true
   ```
   enrich는 정책을 실행한 시점의 복사본을 쓴다. games가 바뀌면 `games-name`을 다시 실행해야 새 게임 이름이 붙는다. `users-name`은 타이머가 1분마다 다시 실행한다.
4. `PUT _ingest/pipeline/clickstream-game-name` ← `clickstream-pipeline.json` (게임 이름: `name_ko`, 없으면 `name`)
5. `PUT _index_template/clickstream` ← `clickstream-template.json` (`index.default_pipeline`, `game_name`·`user_name` keyword)
6. 이미 있는 인덱스: `PUT clickstream-*/_mapping {"properties":{"user_name":{"type":"keyword"}}}` →
   `POST clickstream-*/_update_by_query?pipeline=clickstream-game-name&conflicts=proceed` → `POST clickstream-*/_refresh`

**순서 주의 (11/26 겪은 문제):** 파이프라인(4)을 템플릿(5)보다 먼저 바꾸면 그사이 들어온 기록 때문에 ES가 `user_name`을 **text**로 자동 생성한다.
그러면 6의 `_mapping`이 `cannot be changed from type [text] to [keyword]`로 실패하고 Kibana에서 타입 충돌이 난다.
그날 인덱스는 `_reindex`로 `clickstream-YYYY.MM.dd-r`에 복사한 뒤 원래 인덱스를 지워 해결했다(223건 그대로). 새 칸은 **템플릿 → 매핑 → 파이프라인** 순서로 넣는다.

### 사용자 이름 동기화 (elk)
| 항목 | 값 |
|---|---|
| 스크립트 | `/usr/local/bin/es-users-sync` (root 755) ← `es-users-sync` (Python 3 표준 라이브러리 + `mariadb` 클라이언트) |
| 비밀 값 | `/etc/es-users-sync/env` (root 600, 폴더 700) ← `es-users-sync.env.example` |
| 서비스·타이머 | `/etc/systemd/system/es-users-sync.{service,timer}` ← 이 폴더. 부팅 2분 뒤, 이후 1분마다 |
| MariaDB 계정 | `es_reader@10.0.2.103`: `gamenuri.users`의 `user_id`, `nickname`, `email` 세 칸만 SELECT, 연결 2개. Replica(`mariadb-re`)에서 읽는다 (11/26, mariadb-pr에서 생성) |
| 표시 이름 | `nickname` → 없으면 이메일 `@` 앞 → 없으면 `user-<번호>`. 이메일 전체는 ES에 넣지 않는다. **팀 내부용** (Kibana에 이름이 보인다) |

```bash
# elk, adminb
sudo dnf install -y mariadb      # 클라이언트
sudo install -m 755 infra/elk/es-users-sync /usr/local/bin/
sudo install -d -m 700 /etc/es-users-sync
sudo install -m 600 infra/elk/es-users-sync.env.example /etc/es-users-sync/env
sudo vi /etc/es-users-sync/env   # 비밀번호 두 곳
sudo bash -c 'set -a; . /etc/es-users-sync/env; set +a; /usr/local/bin/es-users-sync --no-enrich'   # 정책 만들기 전 1회
sudo install -m 644 infra/elk/es-users-sync.service infra/elk/es-users-sync.timer /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now es-users-sync.timer   # 정책(users-name)을 만든 뒤에 켠다
sudo journalctl -u es-users-sync.service -n 5 --no-pager                            # "users N건 동기화"
```
새로 가입한 사람은 최대 1분 뒤부터 이름이 붙는다. 그 전 기록은 이름 없이 남는다(필요하면 6의 `_update_by_query`).

## 9. Kibana 대시보드 "겜누리 사용자 행동 (clickstream)"

Data View `clickstream`(`clickstream-*`, 시간 `occurred_at`), `reviews`. 발표 때는 시간 Last 15 minutes~1 hour, 자동 새로고침 10초.
사람별 실시간 활동 표는 ES|QL `kibana-user-activity.esql` (이름, 접속·종료 시간, 머문 시간, 총 행동, 검색·상세 조회·스토어 클릭·알림 설정).
- `event` 값: `search`, `view_game`, `click_store`, `set_alert`
- `session_id`는 브라우저에 저장되는 값이라 며칠 이어진다. 그래서 표는 **사람 + 날짜**로 묶는다. 7일로 보면 한 사람이 날짜 수만큼 나온다.
- ES|QL 표는 처음 만든 칸만 기억한다. 쿼리에서 칸 이름을 바꾸면 패널 편집의 Rows/Metrics에서 칸을 다시 추가한다.
- 편집 후 **Save**를 눌러야 다른 브라우저에도 보인다(저장 전 편집은 그 브라우저에만 남는다).
