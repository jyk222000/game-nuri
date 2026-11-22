// 겜누리 MongoDB 인덱스 초기화 (멱등: 여러 번 실행해도 같은 결과)
//
// 실행 (팀장이 mongodb-pr 또는 backend1에서; 비밀번호는 프롬프트로 입력)
//   mongosh "mongodb://mongodb-pr:27017,mongo-se1:27017,mongo-se2:27017/gamenuri_raw?replicaSet=rs0&authSource=admin" \
//     --username gamenuri --file init-collections.js
//
// 컬렉션 (pipeline/connect/mongo-sink-*.json 기준, DB gamenuri_raw)
//   raw      ← raw.price, raw.console, raw.steam, raw.igdb   API 원본(공통 봉투) → TTL 14일
//   reviews  ← raw.steam                                      백업 대상, 분석에 사용 → TTL 없음
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

// 1) raw: 수집 시각(collected_at)이 BSON Date일 때만 TTL 14일
{
  const c = d.raw;
  const total = c.countDocuments({});
  const notDate = c.countDocuments({ collected_at: { $not: { $type: "date" } } });
  if (total === 0) {
    print("건너뜀 raw TTL: 컬렉션이 비어 있어 collected_at 타입을 확인할 수 없음");
  } else if (notDate > 0) {
    const sample = c.findOne({ collected_at: { $not: { $type: "date" } } }, { collected_at: 1 });
    print(`건너뜀 raw TTL: collected_at이 BSON Date가 아닌 문서 ${notDate}/${total}건 (예: ${tojson(sample)})`);
    print("        → Sink가 문자열로 저장 중. Connect 변환(TimestampConverter 등) 후 다시 실행");
  } else {
    ensureIndex("raw", { collected_at: 1 }, { name: "ttl_collected_at_14d", expireAfterSeconds: TTL_SECONDS });
  }
}

// 2) games: game_id 고유 (TTL 없음)
ensureIndex("games", { game_id: 1 }, { name: "uq_game_id", unique: true });

// 3) reviews: recommendationid 고유 (TTL 없음)
//    문서마다 최상위 recommendationid가 있어야 한다. 없는 문서가 둘 이상이면 고유 인덱스가
//    null 중복으로 Sink 쓰기를 막으므로, 전부 있을 때만 만든다.
{
  const c = d.reviews;
  const total = c.countDocuments({});
  const missing = c.countDocuments({ recommendationid: { $exists: false } });
  if (total === 0) {
    print("건너뜀 reviews 고유 인덱스: 컬렉션이 비어 있어 문서 모양을 확인할 수 없음");
  } else if (missing > 0) {
    print(`건너뜀 reviews 고유 인덱스: 최상위 recommendationid가 없는 문서 ${missing}/${total}건`);
    print("        → 현재 Sink는 raw.steam 봉투 전체를 저장하고 리뷰는 payload.reviews[] 안에 있음.");
    print("        → refiner가 리뷰를 한 건씩 펼치기로 확정된 뒤 다시 실행");
  } else {
    ensureIndex("reviews", { recommendationid: 1 }, { name: "uq_recommendationid", unique: true });
  }
}

print("--- 현재 인덱스 ---");
["raw", "games", "reviews"].forEach((n) => {
  print(`${n}: ${d.getCollection(n).getIndexes().map((i) => i.name).join(", ")}`);
});
