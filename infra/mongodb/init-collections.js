// 겜누리 MongoDB 인덱스 초기화 (멱등: 여러 번 실행해도 같은 결과)
//
// 실행 (팀장이 mongodb-pr 또는 backend1에서; 비밀번호는 프롬프트로 입력)
//   mongosh "mongodb://mongodb-pr:27017,mongo-se1:27017,mongo-se2:27017/gamenuri_raw?replicaSet=rs0&authSource=admin" \
//     --username gamenuri --file init-collections.js
//
// 컬렉션 (pipeline/connect/mongo-sink-*.json 기준, DB gamenuri_raw)
//   raw_itad·raw_danawa·raw_steam·raw_igdb(·raw_unknown) ← raw.price·raw.console·raw.steam·raw.igdb
//                                                             API 원본(공통 봉투) → ingested_at 기준 TTL 14일
//   reviews  ← raw.steam(kind=review)                         백업 대상, 분석에 사용 → TTL 없음
//   games    ← refined.games                                  백업 대상, Monstache → ES → TTL 없음
//
// 조건이 맞지 않으면 인덱스를 만들지 않고 이유를 출력한다 (추측으로 만들지 않는다).

const TTL_SECONDS = 14 * 24 * 60 * 60; // 14일
const d = db.getSiblingDB("gamenuri_raw");

function ensureIndex(coll, keys, options) {
  try {
    d.getCollection(coll).createIndex(keys, options); // 같은 정의가 이미 있으면 변화 없음
    print(`OK    ${coll}: ${options.name}`);
  } catch (e) {
    print(`실패  ${coll}: ${options.name} — ${e.message}`);
  }
}

// 1) raw_*: 저장 시각(ingested_at)이 BSON Date일 때만 TTL 14일
//    mongo-sink-raw는 토픽별 컬렉션에 나눠 담고(raw.price→raw_itad, raw.console→raw_danawa,
//    raw.steam→raw_steam, raw.igdb→raw_igdb, 그 밖→raw_unknown) 저장 시각 ingested_at(BSON Date)을 붙인다.
//    원본의 collected_at은 문자열이라 TTL에 쓸 수 없다. TTL은 14일이 지난 문서부터 지우므로,
//    이미 쌓인 문서 중 ingested_at이 14일보다 오래된 것은 인덱스를 만든 뒤 자동으로 지워진다(없으면 지워지는 것도 없다).
const RAW_COLLECTIONS = ["raw_itad", "raw_danawa", "raw_steam", "raw_igdb", "raw_unknown"];
const existing = new Set(d.getCollectionNames());
RAW_COLLECTIONS.forEach((name) => {
  if (!existing.has(name)) {
    print(`건너뜀 ${name} TTL: 컬렉션이 아직 없음`);
    return;
  }
  const c = d.getCollection(name);
  const total = c.countDocuments({});
  const notDate = c.countDocuments({ ingested_at: { $not: { $type: "date" } } });
  if (notDate > 0) {
    print(`건너뜀 ${name} TTL: ingested_at이 BSON Date가 아닌(없는) 문서 ${notDate}/${total}건`);
    print("        → Sink의 InsertField(ingested_at) 설정이 적용되기 전에 쌓인 문서일 수 있음");
  } else {
    ensureIndex(name, { ingested_at: 1 }, { name: "ttl_ingested_at_14d", expireAfterSeconds: TTL_SECONDS });
  }
});

// 2) games: game_id 고유 (TTL 없음)
ensureIndex("games", { game_id: 1 }, { name: "uq_game_id", unique: true });

// 3) reviews: payload.recommendationid 고유 (TTL 없음)
//    raw.steam 리뷰는 1건 단위 봉투(kind=review)로 오고, Steam 리뷰 객체는 payload 안에 있다
//    (docs/contracts/messages/raw.steam.json). 그래서 키는 최상위가 아니라 payload.recommendationid다.
//    없는 문서가 둘 이상이면 고유 인덱스가 null 중복으로 Sink 쓰기를 막으므로, 전부 있을 때만 만든다.
//    (Connect가 kind=review만 reviews에 넣도록 바뀌기 전에는 사양·동접자 문서가 섞여 건너뛴다)
const REVIEW_KEY = "payload.recommendationid";
{
  const c = d.reviews;
  const total = c.countDocuments({});
  const missing = c.countDocuments({ [REVIEW_KEY]: { $exists: false } });
  if (total === 0) {
    print("건너뜀 reviews 고유 인덱스: 컬렉션이 비어 있어 문서 모양을 확인할 수 없음");
  } else if (missing > 0) {
    print(`건너뜀 reviews 고유 인덱스: ${REVIEW_KEY}가 없는 문서 ${missing}/${total}건`);
    print("        → Sink가 raw.steam 전체(사양·동접자 포함)를 저장 중이면 정상. 리뷰(kind=review)만");
    print("          저장하도록 Connect 설정이 바뀐 뒤(pipeline/connect, 남현식), 비운 컬렉션에서 다시 실행");
  } else {
    ensureIndex("reviews", { [REVIEW_KEY]: 1 }, { name: "uq_payload_recommendationid", unique: true });
  }
}

print("--- 현재 인덱스 ---");
[...RAW_COLLECTIONS, "games", "reviews"].forEach((n) => {
  if (!existing.has(n)) return;
  print(`${n}: ${d.getCollection(n).getIndexes().map((i) => i.name).join(", ")}`);
});
