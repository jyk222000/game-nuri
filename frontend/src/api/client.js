// 모든 화면은 이 파일의 api.* 만 쓴다. 경로는 항상 상대경로 /api/...
//
// VITE_API_MODE
//   real (기본) 전부 실서버(nginx → /api). 구글 로그인도 실제로 동작한다.
//   mock        전부 브라우저 안의 목 데이터. Backend·DB 없이 화면만 개발할 때 명시적으로 켠다.
export const API_MODE = import.meta.env.VITE_API_MODE === 'mock' ? 'mock' : 'real';

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

const request = (method, url, body) => (API_MODE === 'mock' ? mock(method, url, body) : real(method, url, body));

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
  // 구글 로그인은 real 모드에서만. mock 에서는 모의 계정으로 로그인한다.
  login: () => (API_MODE === 'real' ? (window.location.href = '/api/auth/google/login') : request('POST', '/api/auth/mock-login')),
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
  reviews: (id, q) => request('GET', `/api/games/${id}/reviews${qs(q)}`),
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
