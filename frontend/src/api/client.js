// 모든 화면은 이 파일의 api.* 만 쓴다. 경로는 항상 상대경로 /api/...
//
// VITE_API_MODE
//   mock   (기본) 전부 브라우저 안의 목 데이터. Backend·DB 없이 개발할 때.
//   hybrid Backend에 이미 구현된 공개 API(REAL_READY)만 실서버로 부르고, 실패하면 목으로 대신한다.
//          나머지는 목. 수집이 시작되어 DB가 채워지는 동안 쓴다.
//   real   전부 실서버(nginx → /api). 모든 API가 구현·적재된 뒤에 쓴다.
// (예전 설정 VITE_USE_MOCK=false 는 real 로 취급한다.)
const MODE = import.meta.env.VITE_API_MODE
  || (import.meta.env.VITE_USE_MOCK === 'false' ? 'real' : 'mock');
export const API_MODE = MODE;

// Backend에 구현되어 있고 로그인이 필요 없는 조회 API. Backend 구현이 늘면 여기에 추가한다.
// (docs/contracts/api.md #10~14, #38 — 가격·이력·최저가·할인 목록·환율·헬스체크)
// (#5~#10 게임·#11~16 가격·타이밍·#25·#29·#32·#33 목록·#36 이벤트·#37 순위·#38 헬스)
// 로그인이 필요한 /api/me/* 는 구글 로그인이 붙기 전까지 목으로 둔다.
const REAL_READY = [
  /^\/api\/health$/,
  /^\/api\/exchange-rates$/,
  /^\/api\/genres$/,
  /^\/api\/tags$/,
  /^\/api\/stats\/api-ranking$/,
  /^\/api\/games$/,
  /^\/api\/games\/(autocomplete|popular|deals|short)$/,
  /^\/api\/games\/players\/(top|low)$/,
  /^\/api\/games\/\d+$/,
  /^\/api\/games\/\d+\/(prices|history|lowest|timing|prediction|requirements)$/,
];
// 로그인 없이 쓰는 쓰기 API
const REAL_READY_POST = [/^\/api\/events$/];

const mock = async (method, url, body) => (await import('./mock/router.js')).mockFetch(method, url, body);

async function real(method, url, body) {
  const res = await fetch(url, {
    method,
    credentials: 'include',
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => null);
  if (!res.ok || data === null) {
    // 계약: 오류는 {"error": {"code", "message"}}. 프런트는 status가 아니라 code로 처리한다.
    const e = new Error(data?.error?.message || '요청에 실패했어요');
    e.status = res.status; e.code = data?.error?.code || 'INTERNAL';
    throw e;
  }
  return data;
}

const warned = new Set();
async function request(method, url, body) {
  if (MODE === 'mock') return mock(method, url, body);
  if (MODE === 'real') return real(method, url, body);
  // hybrid
  const path = url.split('?')[0];
  const ready = method === 'GET' ? REAL_READY : method === 'POST' ? REAL_READY_POST : [];
  if (!ready.some((re) => re.test(path))) return mock(method, url, body);
  try {
    return await real(method, url, body);
  } catch (e) {
    if (!warned.has(path.replace(/\d+/, '{id}'))) {
      warned.add(path.replace(/\d+/, '{id}'));
      console.info(`[api:hybrid] ${path} 실서버 실패(${e.code || e.message}) → 목 데이터로 대신합니다`);
    }
    return mock(method, url, body);
  }
}

// 클릭스트림용 익명 세션 id (브라우저가 만든 UUID, 로그인 쿠키와 무관). 저장소를 못 쓰면 탭마다 새로 만든다.
let memSession = null;
function sessionId() {
  const KEY = 'gamenuri_session_id';
  try {
    let v = localStorage.getItem(KEY);
    if (!v) { v = crypto.randomUUID(); localStorage.setItem(KEY, v); }
    return v;
  } catch {
    return (memSession ||= crypto.randomUUID());
  }
}

const qs = (o = {}) => {
  const p = new URLSearchParams(Object.entries(o).filter(([, v]) => v !== '' && v != null));
  const s = p.toString();
  return s ? `?${s}` : '';
};

export const api = {
  health: () => request('GET', '/api/health'),
  // 인증
  // 구글 로그인은 real 모드에서만. mock·hybrid 에서는 모의 계정으로 로그인한다.
  login: () => (MODE === 'real' ? (window.location.href = '/api/auth/google/login') : request('POST', '/api/auth/mock-login')),
  logout: () => request('POST', '/api/auth/logout'),
  me: () => request('GET', '/api/me'),
  updateMe: (name) => request('PATCH', '/api/me', { name }),
  setSteam: (steam_id) => request('PUT', '/api/me/steam', { steam_id }),
  // 게임
  games: (q) => request('GET', `/api/games${qs(q)}`),
  autocomplete: (q) => request('GET', `/api/games/autocomplete${qs({ q })}`),
  game: (id) => request('GET', `/api/games/${id}`),
  popular: () => request('GET', '/api/games/popular'),
  deals: () => request('GET', '/api/games/deals'),
  short: () => request('GET', '/api/games/short'),
  playersTop: () => request('GET', '/api/games/players/top'),
  playersLow: () => request('GET', '/api/games/players/low'),
  genres: () => request('GET', '/api/genres'),
  tags: () => request('GET', '/api/tags'),
  exchangeRates: () => request('GET', '/api/exchange-rates'),
  // 가격·타이밍
  prices: (id) => request('GET', `/api/games/${id}/prices`),
  history: (id, days = 180, f = {}) => request('GET', `/api/games/${id}/history${qs({ days, ...f })}`),
  lowest: (id) => request('GET', `/api/games/${id}/lowest`),
  timing: (id) => request('GET', `/api/games/${id}/timing`),
  prediction: (id) => request('GET', `/api/games/${id}/prediction`),
  // 리뷰·사양
  reviews: (id) => request('GET', `/api/games/${id}/reviews`),
  reviewSummary: (id) => request('GET', `/api/games/${id}/reviews/summary`),
  requirements: (id) => request('GET', `/api/games/${id}/requirements`),
  specCheck: (id) => request('GET', `/api/games/${id}/spec-check`),
  // 찜·알림
  wishlist: () => request('GET', '/api/me/wishlist'),
  wish: (game_id) => request('POST', '/api/me/wishlist', { game_id }),
  unwish: (game_id) => request('DELETE', `/api/me/wishlist${qs({ game_id })}`),
  alerts: () => request('GET', '/api/me/alerts'),
  addAlert: (game_id, target_price_krw) => request('POST', '/api/me/alerts', { game_id, target_price_krw }),
  patchAlert: (id, b) => request('PATCH', `/api/me/alerts/${id}`, b),
  delAlert: (id) => request('DELETE', `/api/me/alerts/${id}`),
  specs: () => request('GET', '/api/me/specs'),
  setSpecs: (b) => request('PUT', '/api/me/specs', b),
  // 추천
  recommendations: () => request('GET', '/api/me/recommendations'),
  taste: () => request('GET', '/api/me/taste'),
  // 검색·운영
  trending: () => request('GET', '/api/search/trending'),
  recent: () => request('GET', '/api/search/recent'),
  // type: search | view_game | click_store | set_alert (messages/clickstream.json). 실패해도 화면은 계속 동작한다.
  event: (type, data = {}) => request('POST', '/api/events', { type, ...data, session_id: sessionId(), at: new Date().toISOString() }).catch(() => {}),
  apiRanking: () => request('GET', '/api/stats/api-ranking'),
};
