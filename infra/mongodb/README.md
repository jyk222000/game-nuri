# mongodb — 복제 셋 rs0 구축 기록 (2026-11-20)

비밀번호와 키 파일 내용은 쓰지 않는다. 계정 비밀번호는 팀장에게 개인 메시지로 받는다.

## 구성
| 항목 | mongodb-pr | mongo-se1 | mongo-se2 |
|---|---|---|---|
| IP | 10.0.2.104 | 10.0.2.105 | 10.0.2.106 |
| 역할 | PRIMARY (priority 2) | SECONDARY (priority 1) | SECONDARY (priority 1) |
| 버전 | MongoDB 8.0.38, mongosh 2.14.3 | 같음 | 같음 |
| dbPath | `/DATA/mongodb` (약 15G) | 같음 | 같음 |

- 3대 중 1대가 죽어도 과반(2/3)이 남아 자동 선출된다. mongodb-pr는 priority가 높아 복구되면 다시 PRIMARY가 된다.
- Monstache(ES 동기화)는 change stream을 쓰므로 복제 셋이 필요하다.

## 설치 순서 (3대)
```bash
hostname                                         # 대상 VM인지 먼저 확인
sudo cp mongodb-org-8.0.repo.example /etc/yum.repos.d/mongodb-org-8.0.repo
sudo dnf install -y mongodb-org
sudo mkdir -p /DATA/mongodb && sudo chown mongod:mongod /DATA/mongodb && sudo chmod 750 /DATA/mongodb
```
키 파일 (mongodb-pr에서 만들고 나머지 2대로 복사, 3대 `sha256sum` 일치 확인):
```bash
sudo mkdir -p /etc/mongodb
openssl rand -base64 756 | sudo tee /etc/mongodb/keyfile >/dev/null
sudo chown mongod:mongod /etc/mongodb/keyfile && sudo chmod 400 /etc/mongodb/keyfile
sudo restorecon -v /etc/mongodb/keyfile          # /tmp에서 mv해 왔다면 레이블 복구
```
설정과 시작:
```bash
sudo cp mongod.conf.example /etc/mongod.conf
sudo systemctl enable --now mongod
```
복제 셋 구성 (mongodb-pr에서 1회):
```javascript
rs.initiate({_id: "rs0", members: [
  {_id: 0, host: "mongodb-pr:27017", priority: 2},
  {_id: 1, host: "mongo-se1:27017", priority: 1},
  {_id: 2, host: "mongo-se2:27017", priority: 1}]})
// 첫 계정은 localhost 예외로 생성. 비밀번호는 passwordPrompt()로 입력
db.getSiblingDB("admin").createUser({user: "admin", pwd: passwordPrompt(), roles: ["root"]})
```
- 방화벽: 10.0.0.0/16에서만 27017 허용.

## 계정 (인증 DB `admin`)
| 계정 | 권한 | 용도 |
|---|---|---|
| `admin` | root | 관리 전용, 앱에 넣지 않음 |
| `gamenuri` | `gamenuri_raw` readWrite | 앱 (Kafka Connect 등) |
| `monstache` | `gamenuri_raw` read, clusterMonitor | Monstache |

접속 문자열 (호스트 3개, `replicaSet`, `authSource` 모두 필요):
```
mongodb://gamenuri:<비밀번호>@mongodb-pr:27017,mongo-se1:27017,mongo-se2:27017/gamenuri_raw?replicaSet=rs0&authSource=admin
```

## SELinux
- MongoDB 전용 정책(`mongodb-selinux`)이 없어 `mongod_var_lib_t` 레이블을 쓸 수 없다(`Type is invalid`).
- mongod는 `unconfined_service_t`로 실행, `/DATA/mongodb`는 `default_t`. `ausearch -m avc`로 차단 없음 확인, 재부팅 후에도 정상.
- `mongodb-selinux`는 설치하지 않는다 (dbPath를 바꾸면 그 정책을 쓸 수 없음).

## 확인 명령
```javascript
rs.status().members.map(m => `${m.name} ${m.stateStr} health=${m.health}`)
```
장애 전환 테스트: mongodb-pr에서 `sudo systemctl stop mongod` → mongo-se1이 PRIMARY → 다시 start하면 mongodb-pr이 PRIMARY로 복귀 (11/20 확인).

## 겪은 문제
| 문제 | 원인 | 해결 |
|---|---|---|
| `semanage ... mongod_var_lib_t` → `Type is invalid` | 전용 SELinux 정책 없음 | 레이블 없이 시작, `ausearch`로 차단 없음 확인 |
| 키 파일 레이블 `user_tmp_t` | `/tmp`에서 `mv`해 옴 | `restorecon`으로 `etc_t` |
| mongo-se1·se2 SSH 지문 동일 | 같은 이미지를 복제해 만든 VM | 3대 호스트 키 재생성 (`ssh-keygen -A`). 접속 쪽은 `ssh-keygen -R <이름>` |

## 컬렉션·인덱스 (DB `gamenuri_raw`, 기준: `pipeline/connect/mongo-sink-*.json`)
| 컬렉션 | 들어오는 토픽 | 성격 | 인덱스 | TTL | 백업 |
|---|---|---|---|---|---|
| `raw` | `raw.price`, `raw.console`, `raw.steam`, `raw.igdb` | API 원본(공통 봉투) | `collected_at` TTL | **14일** | 안 함(재수집 가능) |
| `reviews` | `raw.steam` | 리뷰 (분석에 사용) | `recommendationid` 고유 | 없음 | **함** |
| `games` | `refined.games` | 게임 정보 (Monstache → ES) | `game_id` 고유 | 없음 | 함 |

- TTL은 `raw`에만 건다. `reviews`·`games`는 분석과 백업 대상이라 지우지 않는다.
- TTL 기준 필드는 **BSON Date 타입의 수집 시각(`collected_at`)**만 쓴다. 문자열이면 TTL이 동작하지 않는다.
- `contracts/topics.md`는 `games` 컬렉션만 적고 `raw`·`reviews`는 Sink 설정에만 있다. contracts에 컬렉션 이름을 추가하는 것이 좋다(제안만, 수정하지 않음).

### 인덱스 생성: `init-collections.js` (멱등)
```bash
hostname   # 정상: mongodb-pr 또는 backend1
mongosh "mongodb://mongodb-pr:27017,mongo-se1:27017,mongo-se2:27017/gamenuri_raw?replicaSet=rs0&authSource=admin" \
  --username gamenuri --file init-collections.js      # 비밀번호는 프롬프트로 입력
```
- 조건이 맞을 때만 만들고, 아니면 `건너뜀 …` 이유를 출력한다. 여러 번 실행해도 같은 결과다.
- **현재 건너뛰는 항목 (2026-11-22 기준 추정, 실행 결과로 확인 필요)**
  - `raw` TTL: Sink가 `JsonConverter`(스키마 없음)로 저장하면 `collected_at`은 ISO 문자열(`"2026-11-19T02:30:00Z"`)이라 TTL이 동작하지 않는다.
    Connect에서 `TimestampConverter` 같은 변환으로 Date로 저장되는지 테스트가 필요하다(pipeline 담당, 미확인).
  - `reviews` 고유 인덱스: 리뷰는 1건 단위 봉투(kind=review)로 오고 Steam 리뷰 객체가 `payload` 안에 있어, 키는 `payload.recommendationid`다(2026-11-23 스크립트 수정, 인덱스 이름 `uq_payload_recommendationid`).
    Sink가 `raw.steam` 전체(사양·동접자 포함)를 저장하는 동안은 `payload.recommendationid`가 없는 문서가 섞여 있어 건너뛴다. `kind=review`만 `reviews`에 넣고 `_id`를 `payload.recommendationid`로 쓰도록 Connect 설정이 바뀐 뒤(pipeline/connect, 남현식) 다시 실행한다.
  - `raw.steam`은 `raw`와 `reviews` 두 컬렉션에 중복 저장된다(Sink 2개). 용량 면에서 확정 필요(pipeline 담당).

## 계정 권한 (최소 권한 정리, 비밀번호 없음)
| 계정 | 필요한 권한 | 이유 |
|---|---|---|
| `gamenuri` (Connect Sink) | `gamenuri_raw` readWrite (현재) | 문서 쓰기, 컬렉션·인덱스 생성. 줄이려면 세 컬렉션에 `insert`·`update`·`find`·`createIndex`만 |
| `monstache` (읽기, change stream) | `gamenuri_raw` read + clusterMonitor (현재) | `read`에 `find`·`changeStream`·`listCollections`가 들어 있다. 쓰기 권한은 필요 없다 |
| `monstache` 재개 정보 | `monstache` DB readWrite | 재시작 시 이어 읽을 위치(resume token) 저장. 기본 DB 이름은 설정에 따라 다름(미확인, 남현식 확인) |
| `backup` (5단계) | `gamenuri_raw` read | `mongodump`에 필요한 `find`·`listCollections`·`listIndexes`. 계정은 팀장이 만든다 |
- Monstache가 실제로 필요한 권한의 정확한 목록은 **미확인**이다(남현식과 확인).
- `admin`(root)은 앱·백업에 쓰지 않는다.

## 남은 일
- [x] 컬렉션 이름·TTL 정책 정리 (위 표). 인덱스 생성은 `init-collections.js` 실행 결과를 확인한 뒤 판단
- [ ] Monstache 연결 시 resume 정보 저장용 `monstache` DB readWrite 권한 보강 검토
- [ ] 모니터링용 계정(clusterMonitor) (11/25)
- [ ] `/var/log/mongodb/mongod.log` 로테이션, THP 경고 처리
