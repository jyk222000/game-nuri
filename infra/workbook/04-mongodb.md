# 4. MongoDB 복제 셋 rs0 (mongodb-pr, mongo-se1, mongo-se2)

수집한 **원본 JSON**(`raw_*`)과 **리뷰**(`reviews`), **게임 정보**(`games`)를 저장합니다. Kafka Connect가 쓰고, Monstache가 읽어 Elasticsearch로 보냅니다.
복제 셋 3대로 만드는 이유는 Monstache가 **change stream**(변경을 실시간으로 받는 기능)을 쓰는데 이것이 복제 셋에서만 동작하기 때문입니다.
(구축 2026-11-20, 정리 작업 2026-11-25, `infra/mongodb/README.md`가 원본 기록)

## 0. 만드는 것
| 항목 | mongodb-pr | mongo-se1 | mongo-se2 |
|---|---|---|---|
| IP | 10.0.2.104 | 10.0.2.105 | 10.0.2.106 |
| 역할 | PRIMARY (priority 2) | SECONDARY (priority 1) | SECONDARY (priority 1) |
| 버전 | MongoDB 8.0.38, mongosh 2.14.3 | 같음 | 같음 |
| dbPath | `/DATA/mongodb` (약 15G) | 같음 | 같음 |

> <- 3대 중 1대가 죽어도 과반(2/3)이 남아 자동으로 새 PRIMARY를 뽑습니다. mongodb-pr는 priority가 높아 복구되면 다시 PRIMARY가 됩니다.

## 1. 설치 (3대 모두)
```
# 대상 VM인지 확인
[admina@mongodb-pr ~]$ hostname

# MongoDB 공식 저장소 등록 (Rocky 10은 redhat/10 저장소, 11/20 HTTP 200 확인)
[admina@mongodb-pr ~]$ sudo cp /opt/game-nuri/repo/infra/mongodb/mongodb-org-8.0.repo.example /etc/yum.repos.d/mongodb-org-8.0.repo

# MongoDB 설치 (mongod 서버 + mongosh 셸 포함)
[admina@mongodb-pr ~]$ sudo dnf install -y mongodb-org

# 데이터 폴더 만들기. 소유자 mongod, 권한 750
[admina@mongodb-pr ~]$ sudo mkdir -p /DATA/mongodb && sudo chown mongod:mongod /DATA/mongodb && sudo chmod 750 /DATA/mongodb
```

## 2. 키 파일 (복제 셋 멤버끼리 인증하는 공유 비밀)
**mongodb-pr에서 한 번만 만들고**, 나머지 2대로 복사합니다. 3대의 내용이 같아야 합니다.
```
# 키 파일 폴더와 무작위 키 만들기 (출력이 화면에 나오지 않게 tee 로 파일에만)
[admina@mongodb-pr ~]$ sudo mkdir -p /etc/mongodb
[admina@mongodb-pr ~]$ openssl rand -base64 756 | sudo tee /etc/mongodb/keyfile >/dev/null

# 소유자·권한: mongod 만 읽을 수 있게 (400)
[admina@mongodb-pr ~]$ sudo chown mongod:mongod /etc/mongodb/keyfile && sudo chmod 400 /etc/mongodb/keyfile

# SELinux 라벨 복구 (/tmp 에서 옮겨 왔다면 라벨이 user_tmp_t 로 남는다)
[admina@mongodb-pr ~]$ sudo restorecon -v /etc/mongodb/keyfile
```
```
# 3대의 키 파일이 같은지 확인: 해시 값이 3대 모두 같아야 한다
[admina@mongodb-pr ~]$ sudo sha256sum /etc/mongodb/keyfile
[admina@mongo-se1 ~]$ sudo sha256sum /etc/mongodb/keyfile
[admina@mongo-se2 ~]$ sudo sha256sum /etc/mongodb/keyfile
```
> <- **키 파일 내용은 절대 출력·커밋·채팅에 쓰지 않습니다.** 복사는 `scp` 로 하고(파일을 `/tmp` 에 받았다면 위 `restorecon`), 확인은 해시로만 합니다.

## 3. 설정과 시작 (3대)
```
# 설정 파일 복사 (레포: infra/mongodb/mongod.conf.example)
[admina@mongodb-pr ~]$ sudo cp /opt/game-nuri/repo/infra/mongodb/mongod.conf.example /etc/mongod.conf

# 서비스 시작과 부팅 시 자동 시작
[admina@mongodb-pr ~]$ sudo systemctl enable --now mongod
[admina@mongodb-pr ~]$ systemctl status mongod --no-pager
```
설정 파일 핵심:
```
> storage:
>   dbPath: /DATA/mongodb
>   wiredTiger:
>     engineConfig:
>       cacheSizeGB: 0.25          # VM 메모리 1.7G라 최소값으로 제한
> net:
>   port: 27017
>   bindIp: 0.0.0.0
> security:
>   keyFile: /etc/mongodb/keyfile
>   authorization: enabled
> replication:
>   replSetName: rs0
```
> <- `cacheSizeGB: 0.25`: 이 VM들은 메모리가 1.7GB라 MongoDB가 메모리를 다 쓰지 않게 제한합니다.
> <- `authorization: enabled` 라서 계정 없이는 아무것도 못 합니다. 첫 계정은 아래 4장의 **localhost 예외**로 만듭니다.

## 4. 복제 셋 만들기 (mongodb-pr 에서 1회)
```
# mongodb-pr 에서 mongosh 접속 (아직 계정이 없어서 localhost 로만 가능)
[admina@mongodb-pr ~]$ mongosh

# 복제 셋 구성: mongodb-pr 가 priority 2 라서 항상 PRIMARY 를 우선한다
> rs.initiate({_id: "rs0", members: [
>   {_id: 0, host: "mongodb-pr:27017", priority: 2},
>   {_id: 1, host: "mongo-se1:27017", priority: 1},
>   {_id: 2, host: "mongo-se2:27017", priority: 1}]})

# 첫 관리자 계정 (localhost 예외로 가능). 비밀번호는 입력창으로 받는다
> db.getSiblingDB("admin").createUser({user: "admin", pwd: passwordPrompt(), roles: ["root"]})
```
> <- `passwordPrompt()` 가 비밀번호를 입력창으로 받아 명령 기록에 남지 않게 합니다.
> <- 멤버 이름(`mongo-se1`)은 `/etc/hosts` 로 해석되므로 [01-공통준비.md](01-공통준비.md)가 먼저 끝나 있어야 합니다.

```
# 상태 확인: 한 대는 PRIMARY, 두 대는 SECONDARY, health=1
> rs.status().members.map(m => `${m.name} ${m.stateStr} health=${m.health}`)
```

## 5. 계정 (인증 DB `admin`)
관리자(`admin`)로 접속해서 만듭니다. 비밀번호는 모두 `passwordPrompt()`로 입력하고 문서·채팅에 쓰지 않습니다.
| 계정 | 권한 | 용도 |
|---|---|---|
| `admin` | root | 관리 전용, **앱에 넣지 않음** |
| `gamenuri` | `gamenuri_raw` readWrite | 앱(Kafka Connect 등) |
| `monstache` | `gamenuri_raw` read + clusterMonitor | Monstache(ES 동기화) |
| `backup` | `gamenuri_raw` read | 백업(`mongodump`), 팀장이 만듦. ⚠ 생성 여부 미확인 |

```
# 앱 계정 예시 (비밀번호는 입력창으로)
> db.getSiblingDB("admin").createUser({user: "gamenuri", pwd: passwordPrompt(),
>   roles: [{role: "readWrite", db: "gamenuri_raw"}]})
```
접속 문자열 (**호스트 3개, `replicaSet`, `authSource` 셋 다 필요**):
```
> mongodb://gamenuri:<비밀번호>@mongodb-pr:27017,mongo-se1:27017,mongo-se2:27017/gamenuri_raw?replicaSet=rs0&authSource=admin
```
> <- 비밀번호에 `@`, `:`, `/` 같은 기호가 있으면 URL 인코딩해야 합니다.

## 6. SELinux
- MongoDB 전용 정책(`mongodb-selinux`)이 없어 `mongod_var_lib_t` 라벨을 쓸 수 없습니다(`semanage fcontext ... mongod_var_lib_t` 는 `Type is invalid`).
- mongod는 `unconfined_service_t` 로 실행되고 `/DATA/mongodb` 는 `default_t` 입니다. `sudo ausearch -m avc` 로 **차단 기록이 없음**을 확인했고 재부팅 후에도 정상입니다.
- `mongodb-selinux` 는 설치하지 않습니다(dbPath를 `/DATA` 로 바꾸면 그 정책을 쓸 수 없음).

```
# 차단 기록이 있는지 확인 (아무것도 안 나오면 정상)
[admina@mongodb-pr ~]$ sudo ausearch -m avc -ts recent
```

## 7. 장애 전환 시험 (11/20 통과)
```
# (mongodb-pr) PRIMARY 를 일부러 멈춘다 — 서비스 영향이 없는 시간에
[admina@mongodb-pr ~]$ sudo systemctl stop mongod

# (mongo-se1) mongosh 에서 확인: mongo-se1 이 PRIMARY 로 바뀌었는지
> rs.status().members.map(m => `${m.name} ${m.stateStr}`)

# (mongodb-pr) 다시 켜면 priority 가 높아 PRIMARY 로 복귀
[admina@mongodb-pr ~]$ sudo systemctl start mongod
```

## 8. 컬렉션·인덱스·TTL (DB `gamenuri_raw`)
기준은 `pipeline/connect/mongo-sink-*.json` 입니다.
| 컬렉션 | 들어오는 곳 | 성격 | 인덱스 | TTL | 백업 |
|---|---|---|---|---|---|
| `raw_itad` `raw_danawa` `raw_steam` `raw_igdb` (`raw_unknown`) | `raw.price` `raw.console` `raw.steam` `raw.igdb` (목록에 없는 토픽) | API 원본(공통 봉투) | `ingested_at` TTL | **14일** | 안 함(재수집 가능) |
| `reviews` | `raw.steam`(`kind=review`만) | 리뷰(분석에 사용) | `payload.recommendationid` 고유 | 없음 | **함** |
| `games` | `refined.games` | 게임 정보(Monstache → ES) | `game_id` 고유 | 없음 | 함 |
| `unmatched` | `refined.unmatched` | 정제 매칭 실패 기록 | 없음 | 없음 | 안 함 |

> <- **TTL(Time To Live)** 은 문서의 날짜 필드를 보고 정한 기간(14일)이 지나면 MongoDB가 문서를 자동 삭제하는 기능입니다. 날짜 필드는 반드시 **BSON Date 형식**이어야 합니다. 숫자(밀리초)로 저장돼 있으면 TTL이 무시합니다.

인덱스는 스크립트 하나로 만듭니다(여러 번 실행해도 같은 결과).
```
# 스크립트가 있는 폴더로 이동 (레포는 backend1 에 있음. mongodb-pr 에는 레포가 없어서 scp 로 파일 하나만 복사해도 된다)
[admina@backend1 ~]$ cd /opt/game-nuri/repo/infra/mongodb

# 인덱스 생성: 조건이 맞을 때만 만들고, 아니면 '건너뜀 + 이유'를 출력한다. 비밀번호는 프롬프트로
[admina@backend1 mongodb]$ mongosh "mongodb://mongodb-pr:27017,mongo-se1:27017,mongo-se2:27017/gamenuri_raw?replicaSet=rs0&authSource=admin" --username gamenuri --file init-collections.js
```
> <- 성공 기준(11/25 실행 결과): `OK raw_itad: ttl_ingested_at_14d` 가 `raw_itad`, `raw_danawa`, `raw_steam`, `raw_igdb` 마다 나오고, `OK games: uq_game_id`, `OK reviews: uq_payload_recommendationid`.
> `raw_unknown` 은 컬렉션이 아직 없어 건너뜀이 정상입니다.
> <- 서버에 `mongosh` 가 없으면 backend1에는 설치돼 있지 않을 수 있습니다(⚠ 미확인). 그 경우 mongodb-pr에 이 스크립트 파일만 복사해서 실행합니다.

## 9. 2026-11-25 정리 작업 기록 (이중 저장 해소, TTL 적용)
**문제**: `raw.steam` 토픽의 리뷰가 `raw_steam` 과 `reviews` 두 곳에 저장됐고(약 45만 건 중복), `ingested_at` 이 숫자라 TTL이 걸리지 않았습니다.
순서(서버 데이터를 바꾸는 작업이라 한 단계씩 확인하고 진행했습니다).

**1) 필터 적용 확인** (kafka1, 읽기 전용): `mongo-sink-raw` 커넥터에 리뷰 제외 필터(`skipReview`, PR #127, 남현식)가 있는지.
```
[admina@kafka1 ~]$ curl -s localhost:8083/connectors/mongo-sink-raw/config | python3 -c "import sys,json; c=json.load(sys.stdin); print(c.get('transforms')); print(c.get('transforms.skipReview.filter.type'))"
> skipReview,ingested,ingestedDate
> exclude
```
> <- 필터가 없는 채로 아래 삭제를 하면 다음 수집(매일 05:00)에서 리뷰가 다시 쌓입니다.

**2) 같은 리뷰인지 대조** (mongosh, 읽기 전용): 건수와 샘플 200건이 `reviews` 에 있는지.
```
> use gamenuri_raw
> db.raw_steam.countDocuments({kind: "review"})
> db.reviews.countDocuments({})
> const ids = db.raw_steam.aggregate([{$match: {kind: "review"}}, {$sample: {size: 200}}, {$project: {_id: 0, id: "$payload.recommendationid"}}]).toArray().map(d => d.id);
> print(ids.length, db.reviews.countDocuments({"payload.recommendationid": {$in: ids}}))
```
> <- 11/25 결과: 451,620 = 451,620, 샘플 `200 200`.

**3) 삭제** `⚠ 되돌릴 수 없음` — 원본은 `reviews`와 백업에 있어야 합니다. 직전에 건수 비교로 한 번 더 막습니다.
```
> const raw = db.raw_steam.countDocuments({kind: "review"});
> const rev = db.reviews.countDocuments({});
> if (raw <= rev) { print(db.raw_steam.deleteMany({kind: "review"})); } else { print("건수가 맞지 않아 중단"); }
> db.raw_steam.distinct("kind")
```
> <- 11/25 결과: `deletedCount: 451620`, 남은 종류 `app_details`, `player_count`, `review_summary`, `reviews` 는 451,620건 그대로.

**4) `ingested_at` 숫자 → 날짜 변환** (`raw_*` 만). `reviews` 는 바꾸면 Monstache가 45만 건을 ES에 다시 색인하고, `unmatched` 는 TTL이 없어 건드리지 않습니다.
```
# 현재 숫자/날짜 분포 (읽기 전용)
> ["raw_itad","raw_danawa","raw_steam","raw_igdb"].forEach(c => print(c, "숫자", db[c].countDocuments({ingested_at: {$type: "number"}}), "날짜", db[c].countDocuments({ingested_at: {$type: "date"}})))

# 시험으로 1건만 변환하고 날짜로 보이는지 확인
> db.raw_steam.updateOne({ingested_at: {$type: "number"}}, [{$set: {ingested_at: {$toDate: "$ingested_at"}}}])
> db.raw_steam.find({ingested_at: {$type: "date"}}, {ingested_at: 1}).sort({ingested_at: 1}).limit(2)

# 전체 변환 (이미 날짜인 문서는 조건에 안 걸려 다시 실행해도 안전)
> ["raw_itad","raw_danawa","raw_steam","raw_igdb"].forEach(c => print(c, db[c].updateMany({ingested_at: {$type: "number"}}, [{$set: {ingested_at: {$toDate: "$ingested_at"}}}]).modifiedCount))
```
> <- 11/25 결과: `raw_itad` 4,995 / `raw_danawa` 3,948 / `raw_steam` 21,998(+시험 1) / `raw_igdb` 3,558건.

**5) TTL 생성 전 확인**: 14일 이상 된 문서가 있으면 인덱스를 만드는 순간 자동 삭제됩니다.
```
> ["raw_itad","raw_danawa","raw_steam","raw_igdb"].forEach(c => print(c, db[c].countDocuments({ingested_at: {$lt: new Date(Date.now() - 14*86400000)}})))
```
> <- 11/25 결과: 모두 0건. 그다음 8장의 `init-collections.js` 를 다시 실행했습니다.

**6) 내일(05:00 수집) 이후 확인**: `db.raw_steam.countDocuments({kind: "review"})` 가 **0** 이면 필터가 동작하는 것입니다. ⚠ 미확인(작성 시점 기준).

## 10. 겪은 문제
| 문제 | 원인 | 해결 |
|---|---|---|
| `semanage ... mongod_var_lib_t` → `Type is invalid` | 전용 SELinux 정책 없음 | 라벨 없이 시작, `ausearch` 로 차단 없음 확인 |
| 키 파일 라벨이 `user_tmp_t` | `/tmp` 에서 `mv` 해 옴 | `restorecon` 으로 `etc_t` |
| mongo-se1·se2 SSH 지문이 같음 | 같은 이미지를 복제해 만든 VM | 3대 호스트 키 재생성(`ssh-keygen -A`). 접속하는 쪽은 `ssh-keygen -R <이름>` |
| `Command aggregate requires authentication` | 로그인 없이 mongosh 접속 | `mongosh ... --username <계정> --authenticationDatabase admin -p` 로 접속(비밀번호는 입력창) |
| 같은 문서의 `ingested_at` 이 숫자라 TTL 미적용 | Connect가 스키마 없는 JSON으로 저장, 시각을 숫자로 넣음 | Connect의 TimestampConverter(#82)로 새 문서는 Date, 옛 문서는 9장 4)로 변환 |

## 11. 남은 일
- [ ] Monstache 재개 정보 저장용 `monstache` DB readWrite 권한 보강 검토(남현식과)
- [ ] 모니터링용 계정(clusterMonitor)
- [ ] `/var/log/mongodb/mongod.log` 로테이션, THP 경고 처리
