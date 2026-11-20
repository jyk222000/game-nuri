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

## 남은 일
- [ ] 컬렉션·인덱스·TTL(원본 14일)을 `docs/contracts/`에 확정 후 생성. TTL 필드는 BSON Date 타입이어야 동작
- [ ] Monstache 연결 시 resume 정보 저장용 `monstache` DB readWrite 권한 보강 검토
- [ ] 모니터링용 계정(clusterMonitor) (11/25)
- [ ] `/var/log/mongodb/mongod.log` 로테이션, THP 경고 처리
