# Monstache

MongoDB `gamenuri_raw.games` → ES `games`, `gamenuri_raw.reviews` → ES `reviews`, `gamenuri_raw.game_aliases` → ES `game_aliases`(11/27) 실시간 동기화.
elk VM에서 systemd 서비스로 돈다. 비밀번호는 쓰지 않는다.

## 1. 구성 (2026-11-23 설치)

| 항목 | 값 |
|---|---|
| 버전 | Monstache **6.8.0** (GitHub 릴리스 `monstache_v6.8.0_linux_x86_64.tar.gz`, `checksums.txt`로 확인) |
| 호환 | ES **8.19.25** + MongoDB **8.0.38**에서 추가·수정·삭제 동기화 확인 (시험 문서 3건, 11/23). 대안(Kafka Connect ES Sink)은 쓰지 않는다 |
| 실행 파일 | `/usr/local/bin/monstache` (root, 755, SELinux `bin_t`) |
| 설정 | `/etc/monstache/monstache.toml` ← 이 폴더의 `monstache.toml` |
| 비밀 값 | `/etc/monstache/monstache.env` (root 600) ← `monstache.env.example` 참고 |
| 서비스 | `/etc/systemd/system/monstache.service` ← `monstache.service` (`DynamicUser`, 실패 시 10초 후 재시작) |
| MongoDB 계정 | `monstache`: `gamenuri_raw` read, `clusterMonitor`, `monstache` DB readWrite(resume 기록용, 11/23 추가. 11/27 `resume = false`로 지금은 쓰지 않음) |
| ES 계정 | `elastic` (`docs/decisions.md` 11/23) |

## 2. 인덱스 (Monstache를 켜기 **전에** 만든다)

인덱스가 없으면 ES가 첫 문서를 보고 nori 없이 자동으로 만든다. 그러면 지우고 다시 만들어야 한다.

| 인덱스 | 매핑 | 원본 | 비고 |
|---|---|---|---|
| `games` | `games-index.json` | MongoDB `games` (`refined.games`) | 매핑에 없는 필드(`summary`, `rating` 등)는 ES가 자동 추가. `genres`·`platforms`는 `refined.games`에 없어 비어 있음 |
| `game_aliases` | `game-aliases-index.json` | MongoDB `game_aliases` (`refined.game_aliases` → `mongo-sink-game-aliases`) | 문서 1개 = 별칭 1개 (`game_id`, `alias`, `source`, `reviewed`). Backend 검색(#5, PR #182)이 `games`와 함께 읽는다. `alias`는 nori + `alias.raw` keyword |
| `reviews` | `reviews-index.json` | MongoDB `reviews` (`raw.steam` `kind=review` 봉투) | `monstache.toml`의 `[[script]]`가 `payload`를 최상위로 펼친다. 게임 키는 **`steam_appid`** (IGDB `game_id` 아님). 검색은 `review`, ⑤ 키워드 집계는 **`review.nouns`** (명사만, 2글자 이상, 불용어 제외, `fielddata`는 이 필드에만) |

11/23 기준 `games` 1000건(975KB), `reviews` 451,368건(155MB), `review.nouns` fielddata 12MB(힙 2GB). 11/27 `game_aliases` 3,827건.

⑤ 키워드 예시 (게임별·추천/비추천별 명사 TOP 10):
```
GET reviews/_search
{ "size": 0, "query": { "term": { "steam_appid": 1245620 } },
  "aggs": { "by_vote": { "terms": { "field": "voted_up" },
    "aggs": { "keywords": { "terms": { "field": "review.nouns", "size": 10 } } } } } }
```
그 게임에서만 유난히 많은 말은 `terms` 대신 `significant_terms`.

복사본은 0 (`number_of_replicas: 0`, ES가 1대라 1이면 상태가 yellow).

만들기 (Kibana Dev Tools 또는 elk에서 curl, `-u elastic`은 비밀번호를 프롬프트로 묻는다):
```bash
curl -s -u elastic -X PUT http://elk:9200/games   -H 'Content-Type: application/json' --data-binary @games-index.json
curl -s -u elastic -X PUT http://elk:9200/reviews -H 'Content-Type: application/json' --data-binary @reviews-index.json
curl -s -u elastic -X PUT http://elk:9200/game_aliases -H 'Content-Type: application/json' --data-binary @game-aliases-index.json
```

## 3. 설치
```bash
# elk, adminb
V=v6.8.0; mkdir -p ~/monstache-dl && cd ~/monstache-dl
curl -sSLO https://github.com/rwynn/monstache/releases/download/$V/monstache_${V}_linux_x86_64.tar.gz
curl -sSLO https://github.com/rwynn/monstache/releases/download/$V/checksums.txt
sha256sum -c checksums.txt --ignore-missing          # OK 확인
tar -xzf monstache_${V}_linux_x86_64.tar.gz
sudo install -o root -g root -m 755 monstache /usr/local/bin/monstache   # mv 대신 install (SELinux 라벨)
sudo install -d -m 755 /etc/monstache
sudo install -m 644 <레포>/infra/monstache/monstache.toml /etc/monstache/
sudo install -m 600 <레포>/infra/monstache/monstache.env.example /etc/monstache/monstache.env
sudo vi /etc/monstache/monstache.env                  # <비밀번호> 두 곳을 편집기로 채움
sudo install -m 644 <레포>/infra/monstache/monstache.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now monstache
```

## 4. 확인
```bash
systemctl is-active monstache
sudo journalctl -u monstache --no-pager -n 20   # Successfully connected to Elasticsearch / MongoDB, Watching changes on ...
```
건수 비교: MongoDB `db.games.countDocuments()` = ES `GET games/_count` (11/23: 1000 = 1000).

`game_aliases` (11/27):

| 위치 | 건수 | 비고 |
|---|---|---|
| Kafka `refined.game_aliases` | 19,130 메시지 | 다시 수집할 때마다 같은 별칭이 또 온다. 가장 오래된 오프셋 0 (지워진 것 없음) |
| MariaDB `game_aliases` | 3,712 | 모두 `source=igdb` (llm 0) |
| MongoDB `game_aliases` | 3,827 | `game_id + alias` 완전 중복 0 |
| ES `game_aliases` | 3,827 | MongoDB와 같음 |

MariaDB보다 115건 많은 것은 `Reanimal`/`REANIMAL`처럼 **대소문자·공백만 다른 별칭 108건 + 악센트 등 비교 규칙 차이 7건**이다.
MariaDB는 PK 비교가 대소문자를 구분하지 않아 한 줄로 합치고, MongoDB는 따로 저장한다. 검색 결과는 같다(ES 분석기가 소문자로 바꾼다).
확인 방법: MongoDB에서 `{game_id, alias}`로 묶어 2개 이상인 묶음 수(0이어야 함), `{game_id, toLower(trim(alias))}`로 묶은 여분 수.

## 5. 매핑을 바꿀 때
1. 이 폴더의 `*-index.json` 수정 (PR)
2. ES에서 인덱스 삭제 → 새 매핑으로 생성
3. `sudo systemctl restart monstache` → 시작할 때 direct-read로 MongoDB 전체를 다시 복사 (같은 `_id`라 중복 없음)
4. 건수 비교

## 6. 재시작 때 실시간 반영이 멈춘 문제 (11/27)

game_aliases를 추가하고 재시작하자 로그에 다음이 나왔다. 프로세스는 `active`였지만 세 컬렉션 모두 실시간 반영이 멈췄다.
```
Resuming from timestamp {T:1795723695 I:3}
ERROR Error resuming change stream: (ChangeStreamHistoryLost) ... the resume point may no longer be in the oplog.
```
- 원인: `resume = true`는 마지막으로 처리한 변경 시각부터 이어 읽는다. 이 시각은 **감시하는 컬렉션에 변경이 있을 때만** 갱신된다.
  games·reviews에 14시간 동안 변경이 없는 사이 다른 컬렉션(raw 수집, TTL 삭제)의 쓰기로 oplog가 밀려 그 시각이 지워졌다.
  이번 설정 변경과 상관없이, 오래 조용하다가 재시작하면 언제든 생기는 문제다.
- 해결: `resume = false`. 시작할 때마다 direct-read로 전체를 다시 맞추고(같은 `_id`라 중복 없음) 그 시점부터 실시간으로 읽으므로 빠지는 데이터가 없다.
  대가는 재시작할 때마다 reviews 45만 건을 다시 복사하는 것(수 분). 저장 위치 문서를 지우는 방법은 같은 문제가 다시 나서 쓰지 않았다.
- 확인: 재시작 로그에 `Resuming from timestamp`가 없고 `Watching changes on collection` 세 줄만 있다.

## 7. 나중에 챙길 것
- `games`의 `genres`·`platforms`: 실제 데이터에 없다. 장르·플랫폼 필터가 필요하면 정제에서 MongoDB 문서에 넣거나 매핑에서 뺀다 (팀 결정)
- "사이버펑크"처럼 nori 사전에 없는 합성어는 부분 검색("펑크")이 안 된다 → 사용자 사전 또는 n-gram 검토
- `review.nouns`의 품사(`stoptags`)·불용어(`review_stop`)는 결과를 보며 조정한다. 바꾸면 5장 순서대로 인덱스를 다시 만든다(45만 건 재복사, 수 분).
  미리 시험은 인덱스 없이 `POST _analyze`에 tokenizer·filter를 직접 넣어 한다.
- `타격감`→`타격`, `최적화`→`최적`처럼 접미사(XSN)가 떨어진다. 키워드로는 쓸 만해서 그대로 둔다
