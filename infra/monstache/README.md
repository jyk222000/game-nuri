# Monstache
- 역할: MongoDB `gamenuri_raw.games` → ES `games`, `gamenuri_raw.reviews` → ES `reviews` 실시간 동기화 (요구사항 #2, ⑤ 리뷰 키워드 추출)
- 첫날 할 일: 설치할 ES 버전과 Monstache 버전 호환 확인. 안 되면 Kafka Connect ES Sink(refined.games → ES)로 대체하고 `docs/decisions.md`에 기록
- ES `games` 인덱스는 Monstache 실행 **전에** nori 분석기 매핑으로 먼저 만든다 (`games-index.json`)
- 실행: `MONSTACHE_MONGO_URL=... monstache -f monstache.toml` (systemd 서비스로 등록)
