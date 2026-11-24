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
| `raw_itad` · `raw_danawa` · `raw_steam` · `raw_igdb` (· `raw_unknown`) | `raw.price` · `raw.console` · `raw.steam` · `raw.igdb` (목록에 없는 토픽) | API 원본(공통 봉투) | `ingested_at` TTL | **14일** | 안 함(재수집 가능) |
| `reviews` | `raw.steam`(`kind=review`만) | 리뷰 (분석에 사용) | `payload.recommendationid` 고유 | 없음 | **함** |
| `games` | `refined.games` | 게임 정보 (Monstache → ES) | `game_id` 고유 | 없음 | 함 |
| `unmatched` | `refined.unmatched` | 정제 매칭 실패 기록 | 없음(필요하면 추가) | 없음 | 안 함(로그용) |

- 컬렉션 이름은 `pipeline/connect/mongo-sink-raw.json`의 `topic.override.*`가 정한다(예전 문서의 `raw` 한 컬렉션이 아니다, 2026-11-23 실제 설정에 맞춤).
- TTL은 `raw_*`에만 건다. `reviews`·`games`는 분석과 백업 대상이라 지우지 않는다.
- TTL 기준 필드는 Sink가 저장 시각으로 붙이는 **`ingested_at`(BSON Date)**이다. 원본의 `collected_at`은 문자열이라 TTL에 쓸 수 없다.
- `contracts/topics.md`는 `games` 컬렉션만 적고 `raw_*`·`reviews`는 Sink 설정에만 있다. contracts에 컬렉션 이름을 추가하는 것이 좋다(제안만, 수정하지 않음).

### 인덱스 생성: `init-collections.js` (멱등)
```bash
hostname   # 정상: mongodb-pr 또는 backend1
mongosh "mongodb://mongodb-pr:27017,mongo-se1:27017,mongo-se2:27017/gamenuri_raw?replicaSet=rs0&authSource=admin" \
  --username gamenuri --file init-collections.js      # 비밀번호는 프롬프트로 입력
```
- 조건이 맞을 때만 만들고, 아니면 `건너뜀 …` 이유를 출력한다. 여러 번 실행해도 같은 결과다.
- **2026-11-25 실행 결과 (mongodb-pr, 모두 적용됨)**
  - `raw_itad`·`raw_danawa`·`raw_steam`·`raw_igdb`: `ttl_ingested_at_14d` 생성(14일). `raw_unknown`은 컬렉션이 아직 없어 건너뜀.
  - `games`: `uq_game_id`, `reviews`: `uq_payload_recommendationid` 생성.
- **적용하기 전에 한 정리 (같은 날, 모두 mongosh에서 직접 실행)**
  1. 리뷰 이중 저장 해소: `mongo-sink-raw`에서 `kind=review`를 제외하는 필터(`skipReview`, #127)를 서버에 적용한 뒤, `raw_steam`에 이미 쌓여 있던 리뷰 451,620건을 삭제했다. 삭제 전에 `reviews`와 건수(451,620 = 451,620)·샘플 200건 대조로 같은 리뷰인지 확인했고, 삭제 후 `reviews`는 그대로, `raw_steam`은 33,999건(`app_details`·`player_count`·`review_summary`)이 남았다.
  2. `ingested_at` 변환: 옛 문서는 Long(밀리초 숫자)이라 TTL이 동작하지 않았다. `raw_*`의 숫자 값을 `$toDate`로 BSON Date로 바꿨다(`raw_itad` 4,995 / `raw_danawa` 3,948 / `raw_steam` 21,999 / `raw_igdb` 3,558건). `reviews`와 `unmatched`는 건드리지 않았다(`reviews`를 바꾸면 Monstache가 ES에 전부 다시 색인하고, `unmatched`는 TTL이 없다).
  3. TTL을 만들기 전에 `ingested_at`이 14일보다 오래된 문서가 없는 것을 확인했다(전부 0건). 인덱스를 만든 순간 지워진 문서는 없다.
- 새 문서의 `ingested_at`은 Sink의 TimestampConverter(#82)로 처음부터 Date다. 옛 값이 다시 섞이면 `init-collections.js`가 그 컬렉션의 TTL을 건너뛰므로 같은 변환(`updateMany({ingested_at:{$type:"number"}}, [{$set:{ingested_at:{$toDate:"$ingested_at"}}}])`)을 `raw_*`에만 한다.
- (참고) `raw_*` TTL 스크립트 동작: `ingested_at`이 BSON Date가 아닌(없는) 문서가 있으면 그 컬렉션은 건너뛴다. 컬렉션이 아직 없어도 건너뛴다. 인덱스를 만든 뒤에는 14일보다 오래된 문서가 자동으로 지워진다.
- `reviews` 고유 인덱스 키는 `payload.recommendationid`다. 리뷰는 1건 단위 봉투(kind=review)로 오고 Steam 리뷰 객체가 `payload` 안에 있다.
- **미확인**: 새 리뷰가 `raw_steam`에 더 쌓이지 않는지(필터 동작)는 다음 `steam-reviews` 수집(매일 05:00) 뒤에 `db.raw_steam.countDocuments({kind:"review"})`가 0인지로 확인한다. TTL이 실제로 14일 뒤부터 오래된 문서를 지우는지도 아직 보지 못했다.

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
- [x] 컬렉션 이름·TTL 정책 정리 (위 표), `raw_*` TTL 적용, 리뷰 이중 저장 해소 (2026-11-25)
- [ ] Monstache 연결 시 resume 정보 저장용 `monstache` DB readWrite 권한 보강 검토
- [ ] 모니터링용 계정(clusterMonitor) (11/25)
- [ ] `/var/log/mongodb/mongod.log` 로테이션, THP 경고 처리
