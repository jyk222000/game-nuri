// 목(mock) 데이터. 실제 서비스에서는 MariaDB/ES 값이 Backend를 통해 내려온다.
// 모든 값은 docs/contracts/api.md 의 응답 형식을 따른다. (시간 UTC, 금액 원화 정수)

export const NOW = new Date('2026-11-21T03:00:00Z');
const DAY = 86400000;

// 재현 가능한 난수 (게임마다 같은 가격 이력이 나오도록)
export function rng(seed) {
  let s = seed % 2147483647;
  if (s <= 0) s += 2147483646;
  return () => (s = (s * 16807) % 2147483647) / 2147483647;
}

export const STORES = {
  steam: { name: 'Steam', kind: 'pc' },
  epic: { name: 'Epic Games', kind: 'pc' },
  gog: { name: 'GOG', kind: 'pc' },
  humble: { name: 'Humble Store', kind: 'pc' },
  fanatical: { name: 'Fanatical', kind: 'pc' },
  gmg: { name: 'Green Man Gaming', kind: 'pc' },
  gamesplanet: { name: 'Gamesplanet', kind: 'pc' },
  microsoft: { name: 'Microsoft Store', kind: 'pc' },
  danawa: { name: '다나와', kind: 'console' },
};

export const GENRES = ['액션', 'RPG', '어드벤처', '시뮬레이션', '인디', '전략', '로그라이크', '슈터'];
export const TAGS = ['오픈월드', '소울라이크', '협동', '스토리 중심', '힐링', '픽셀 아트', '탐험', '1인칭'];

// [id, 이름, 영문, 장르, 플랫폼, 정가, 출시일, 클리어(h), 동접, 긍정비율, 색상 hue, 설명]
const RAW = [
  [119133, '엘든 링', 'Elden Ring', ['액션', 'RPG'], ['pc', 'ps', 'xbox'], 64800, '2022-02-25', 60, 412000, 0.92, 38, '광활한 오픈월드를 탐험하며 엘든 링의 조각을 모으는 액션 RPG.'],
  [1877, '사이버펑크 2077', 'Cyberpunk 2077', ['액션', 'RPG'], ['pc', 'ps', 'xbox'], 66000, '2020-12-10', 26, 98000, 0.86, 55, '나이트 시티를 배경으로 한 오픈월드 SF 액션 RPG.'],
  [119171, '발더스 게이트 3', "Baldur's Gate 3", ['RPG', '전략'], ['pc', 'ps'], 66000, '2023-08-03', 75, 213000, 0.96, 12, '던전 앤 드래곤 규칙 기반의 턴제 RPG. 선택이 이야기를 바꾼다.'],
  [7346, '젤다의 전설: 티어스 오브 더 킹덤', 'Zelda: Tears of the Kingdom', ['어드벤처', '액션'], ['switch'], 79800, '2023-05-12', 60, 0, 0.95, 140, '하이랄의 하늘과 땅, 지하를 누비는 닌텐도 어드벤처.'],
  [113112, '하데스', 'Hades', ['로그라이크', '액션'], ['pc', 'switch', 'ps', 'xbox'], 28000, '2020-09-17', 22, 15000, 0.98, 0, '지하세계를 탈출하는 속도감 있는 로그라이크 액션.'],
  [17000, '스타듀 밸리', 'Stardew Valley', ['시뮬레이션', '인디'], ['pc', 'switch', 'ps', 'xbox'], 16000, '2016-02-26', 55, 62000, 0.98, 100, '농장을 가꾸며 마을 사람들과 어울리는 힐링 시뮬레이션.'],
  [14593, '할로우 나이트', 'Hollow Knight', ['어드벤처', '인디'], ['pc', 'switch', 'ps', 'xbox'], 18000, '2017-02-24', 28, 9000, 0.97, 220, '황폐한 왕국 할로우네스트를 탐험하는 손그림풍 메트로베니아.'],
  [11426, '세키로: 섀도우 다이 트와이스', 'Sekiro: Shadows Die Twice', ['액션'], ['pc', 'ps', 'xbox'], 65800, '2019-03-22', 31, 11000, 0.94, 28, '전국시대 일본을 배경으로 한 검극 액션. 간결하고 날카로운 전투.'],
  [26192, '갓 오브 워', 'God of War', ['액션', '어드벤처'], ['pc', 'ps'], 59800, '2022-01-14', 20, 21000, 0.96, 8, '북유럽 신화로 무대를 옮긴 크라토스의 부자(父子) 여정.'],
  [25076, '레드 데드 리뎀션 2', 'Red Dead Redemption 2', ['액션', '어드벤처'], ['pc', 'ps', 'xbox'], 66000, '2019-12-05', 50, 54000, 0.9, 20, '서부 시대 갱단의 몰락을 그린 오픈월드 대작.'],
  [3277, '데이브 더 다이버', 'Dave the Diver', ['시뮬레이션', '인디', '어드벤처'], ['pc', 'switch', 'ps'], 24000, '2023-06-28', 20, 7000, 0.97, 190, '낮에는 바다를 탐사하고 밤에는 초밥집을 운영하는 하이브리드 게임.'],
  [135400, '팰월드', 'Palworld', ['시뮬레이션', '어드벤처'], ['pc', 'xbox'], 29800, '2024-01-19', 40, 640, 0.84, 160, '팰을 수집하고 부리며 생존·건설하는 오픈월드.'],
  [150080, '헬다이버즈 2', 'Helldivers 2', ['슈터'], ['pc', 'ps'], 49000, '2024-02-08', 30, 61000, 0.82, 48, '4인 협동으로 은하 민주주의를 수호하는 3인칭 슈터.'],
  [9630, '포켓몬스터 스칼렛', 'Pokémon Scarlet', ['RPG', '어드벤처'], ['switch'], 69800, '2022-11-18', 35, 0, 0.7, 350, '팔데아 지방을 자유롭게 누비는 오픈월드 포켓몬.'],
  [90001, '인사이드', 'Inside', ['어드벤처', '인디'], ['pc', 'switch', 'ps', 'xbox'], 22000, '2016-06-29', 4, 1800, 0.96, 205, '정체를 알 수 없는 세계를 가로지르는 소년의 어두운 퍼즐 플랫포머.'],
  [90002, '언패킹', 'Unpacking', ['시뮬레이션', '인디'], ['pc', 'switch', 'ps', 'xbox'], 24000, '2021-11-02', 4, 900, 0.95, 320, '상자를 풀며 한 사람의 삶을 따라가는 힐링 퍼즐.'],
];

// 접속자 적은 온라인 게임(#33) = is_online 이고 동접자 1000 미만 (api.md '서버 정의'). 목은 팰월드·포켓몬 스칼렛.
const ONLINE_ONLY = new Set([150080, 135400, 9630]);

function makeHistory(id, regular, days = 720) {
  const r = rng(id);
  const out = [];
  const interval = 45 + Math.floor(r() * 40);
  const saleLen = 7 + Math.floor(r() * 7);
  const depth = [0.15, 0.25, 0.33, 0.4, 0.5, 0.6][Math.floor(r() * 6)];
  let nextSale = Math.floor(r() * interval);
  for (let d = days; d >= 0; d--) {
    const dayIdx = days - d;
    let pct = 0;
    if (dayIdx >= nextSale && dayIdx < nextSale + saleLen) {
      pct = Math.round((depth + (r() - 0.5) * 0.06) * 100);
    }
    if (dayIdx === nextSale + saleLen) nextSale += interval + Math.floor((r() - 0.5) * 14);
    const price = Math.round((regular * (1 - pct / 100)) / 100) * 100;
    out.push({
      date: new Date(NOW.getTime() - d * DAY).toISOString().slice(0, 10),
      price_krw: price,
      regular_krw: regular,
      discount_pct: pct,
    });
  }
  return out;
}

// 목 원본의 간단한 플랫폼 이름을 ERD 코드(api.md '목업과 ERD가 달랐던 곳' 5번)로 바꾼다.
// game_id → IGDB cover image_id. 여기 없는 게임은 cover_url=null 이라 화면이 색 그라데이션을 쓴다 (실데이터와 같은 동작).
// 확인된 값만 넣는다. 다른 게임은 IGDB 응답의 cover.image_id 를 보고 추가한다.
const COVER_IDS = { 119133: 'co4jni' };

const ERD_PLATFORM = { pc: 'PC', ps: 'PS5', xbox: 'XboxSeries', switch: 'Switch' };

export const GAMES = RAW.map(([id, name, name_en, genres, rawPlatforms, regular, release, ttb, ccu, pos, , summary]) => {
  const history = makeHistory(id, regular);
  const platforms = rawPlatforms.map((p) => ERD_PLATFORM[p]);
  return {
    game_id: id, name, name_en, genres, platforms, regular_krw: regular,
    release_date: release, time_to_beat_hours: ttb, concurrent_players: ccu,
    positive_ratio: pos, summary, online_only: ONLINE_ONLY.has(id),
    cover_url: COVER_IDS[id] ? `https://images.igdb.com/igdb/image/upload/t_cover_big/${COVER_IDS[id]}.jpg` : null,
    tags: TAGS.filter((_, i) => (id + i * 7) % 3 === 0).slice(0, 4),
    steam_app_id: platforms.includes('PC') ? 100000 + (id % 900000) : null,
    history,
  };
});

export const byId = (id) => GAMES.find((g) => g.game_id === Number(id));

// 현재 스토어별 가격: 오늘 Steam 가격을 기준으로 스토어마다 조금씩 다르게.
// 키는 (store, edition, platform, item_condition) — api.md '가격 키'. 중고는 edition=physical + item_condition=used.
export function currentPrices(g) {
  const today = g.history[g.history.length - 1];
  const r = rng(g.game_id * 3);
  const items = [];
  const collected_at = '2026-11-21T02:30:00Z';
  if (g.platforms.includes('PC')) {
    Object.entries(STORES).filter(([, s]) => s.kind === 'pc').forEach(([key], i) => {
      if (key === 'microsoft' && r() < 0.5) return;
      const drift = i === 0 ? 0 : Math.round((r() - 0.45) * 0.18 * 100) / 100;
      const price = Math.max(1000, Math.round((today.price_krw * (1 + drift)) / 100) * 100);
      const pct = Math.max(0, Math.round((1 - price / g.regular_krw) * 100));
      items.push({
        store: key, edition: 'digital', platform: 'PC', item_condition: 'new', price_krw: price,
        regular_krw: g.regular_krw, discount_pct: pct || null, url: '#', collected_at,
      });
    });
  }
  g.platforms.filter((p) => p !== 'PC').forEach((platform) => {
    const base = Math.round((g.regular_krw * (0.8 + r() * 0.15)) / 100) * 100;
    const row = (edition, item_condition, price_krw, regular_krw, discount_pct) => ({
      store: 'danawa', edition, platform, item_condition, price_krw, regular_krw, discount_pct, url: '#', collected_at,
    });
    items.push(row('digital', 'new', base, g.regular_krw, Math.round((1 - base / g.regular_krw) * 100) || null));
    items.push(row('physical', 'new', Math.round((base * 1.04) / 100) * 100, null, null));
    items.push(row('physical', 'used', Math.round((base * 0.7) / 100) * 100, null, null));
  });
  return items;
}

// 가격 이력 한 시리즈(platform·item_condition). 목은 PC 새 상품 이력을 기준으로 다른 시리즈를 비율로 만든다.
export function historySeries(g, platform, itemCondition) {
  if (!g.platforms.includes(platform)) return [];
  const ratio = itemCondition === 'used' ? 0.7 : platform === 'PC' ? 1 : 0.92;
  const store = platform === 'PC' ? 'steam' : 'danawa';
  const edition = platform === 'PC' ? 'digital' : itemCondition === 'used' ? 'physical' : 'digital';
  return g.history.map((h) => ({
    store, edition, platform, item_condition: itemCondition,
    collected_at: `${h.date}T02:30:00Z`,
    price_krw: Math.round((h.price_krw * ratio) / 100) * 100,
    regular_krw: platform === 'PC' || itemCondition === 'new' ? h.regular_krw : null,
    discount_pct: platform === 'PC' ? h.discount_pct : null,
  }));
}

// 할인 이력에서 "세일 구간"을 뽑는다 (예측·타이밍의 근거)
export function saleEvents(history) {
  const ev = [];
  let cur = null;
  for (const h of history) {
    if (h.discount_pct >= 10) {
      if (!cur) cur = { start: h.date, end: h.date, max: h.discount_pct };
      else { cur.end = h.date; cur.max = Math.max(cur.max, h.discount_pct); }
    } else if (cur) { ev.push(cur); cur = null; }
  }
  if (cur) ev.push({ ...cur, ongoing: true });
  return ev;
}

export const REVIEW_SNIPPETS = {
  pos: ['{k} 때문에 시간 가는 줄 몰랐어요', '{k}가 정말 훌륭합니다', '이 가격에 {k}까지… 강추', '{k} 하나만으로도 살 가치 있음'],
  neg: ['{k}가 아쉽습니다', '{k} 때문에 몇 번 접을 뻔했어요', '{k}만 개선되면 완벽할 듯', '할인할 때 사세요, {k}가 걸림'],
};
export const KEYWORDS = {
  default: { pros: ['스토리', '분위기', '그래픽', '재미', '몰입감'], cons: ['최적화', '버그', '반복', '가격'] },
  119133: { pros: ['보스전', '탐험', '아트', '자유도'], cons: ['최적화', '난이도', '카메라'] },
  1877: { pros: ['스토리', '도시 분위기', '음악'], cons: ['버그', '최적화', '초기 완성도'] },
  17000: { pros: ['힐링', '중독성', '모드', '음악'], cons: ['후반 반복'] },
  150080: { pros: ['협동', '타격감', '재미'], cons: ['서버', '밸런스', '버그'] },
};

// game_requirements 텍스트 컬럼 그대로 (api.md '사양'). 구조화는 ⑥ 사양 비교 방식이 정해진 뒤에 추가한다.
export const SPEC_TEMPLATE = (g) => ({
  game_id: g.game_id,
  minimum_text: `OS: Windows 10 64-bit
CPU: Intel Core i5-8400 / AMD Ryzen 3 3300X
그래픽: NVIDIA GTX 1060 3GB / AMD RX 580 4GB
RAM: 12GB
저장공간: 60GB`,
  recommended_text: `OS: Windows 10/11 64-bit
CPU: Intel Core i7-8700K / AMD Ryzen 5 3600X
그래픽: NVIDIA GTX 1070 8GB / AMD RX Vega 56 8GB
RAM: 16GB
저장공간: 60GB`,
  updated_at: '2026-11-19T02:30:00Z',
});

export const TRENDING = [
  ['엘든 링', 132, 'up'], ['발더스 게이트 3', 118, 'same'], ['스타듀 밸리', 97, 'up'],
  ['헬다이버즈', 88, 'down'], ['팰월드', 76, 'up'], ['하데스', 71, 'same'],
  ['사이버펑크', 64, 'down'], ['젤다', 59, 'up'], ['데이브', 51, 'new'], ['세키로', 43, 'same'],
].map(([query, count, change], i) => ({ rank: i + 1, query, count, change }));

export const API_RANKING = [
  ['GET /api/games', 18240], ['GET /api/games/{game_id}/prices', 12033], ['GET /api/games/deals', 9410],
  ['GET /api/games/{game_id}/timing', 7120], ['GET /api/search/trending', 6602], ['GET /api/games/autocomplete', 5987],
  ['GET /api/games/{game_id}', 5510], ['POST /api/events', 4890], ['GET /api/games/{game_id}/reviews/summary', 2301], ['GET /api/me/wishlist', 1244],
].map(([api, calls], i) => ({ rank: i + 1, api, calls }));
