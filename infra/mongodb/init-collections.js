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
["raw", "games", "reviews"].forEach((n) => {
  print(`${n}: ${d.getCollection(n).getIndexes().map((i) => i.name).join(", ")}`);
});
