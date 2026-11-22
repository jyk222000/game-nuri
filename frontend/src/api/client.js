// 모든 화면은 이 파일의 api.* 만 쓴다. 경로는 항상 상대경로 /api/...
// VITE_USE_MOCK=false 로 바꾸면 같은 코드가 실제 Backend(nginx → /api)를 호출한다.
const USE_MOCK = import.meta.env.VITE_USE_MOCK !== 'false';

async function request(method, url, body) {
  if (USE_MOCK) {
    const { mockFetch } = await import('./mock/router.js');
    return mockFetch(method, url, body);
  }
  const res = await fetch(url, {
    method,
    credentials: 'include',
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const e = new Error(data?.error?.message || '요청에 실패했어요');
    e.status = res.status; e.code = data?.error?.code;
    throw e;
  }
  return data;
}

const qs = (o = {}) => {
  const p = new URLSearchParams(Object.entries(o).filter(([, v]) => v !== '' && v != null));
  const s = p.toString();
  return s ? `?${s}` : '';
};

export const api = {
  health: () => request('GET', '/api/health'),
  // 인증
  login: () => (USE_MOCK ? request('POST', '/api/auth/mock-login') : (window.location.href = '/api/auth/google/login')),
  logout: () => request('POST', '/api/auth/logout'),
  me: () => request('GET', '/api/me'),
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
  // 가격·타이밍
  prices: (id) => request('GET', `/api/games/${id}/prices`),
  history: (id, days = 180) => request('GET', `/api/games/${id}/history${qs({ days })}`),
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
  alertLogs: () => request('GET', '/api/me/alerts/logs'),
  notifications: () => request('GET', '/api/me/notifications'),
  setNotifications: (b) => request('PUT', '/api/me/notifications', b),
  specs: () => request('GET', '/api/me/specs'),
  setSpecs: (b) => request('PUT', '/api/me/specs', b),
  // 추천
  recommendations: () => request('GET', '/api/me/recommendations'),
  taste: () => request('GET', '/api/me/taste'),
  // 검색·운영
  trending: () => request('GET', '/api/search/trending'),
  recent: () => request('GET', '/api/search/recent'),
  event: (type, data = {}) => request('POST', '/api/events', { type, ...data, at: new Date().toISOString() }).catch(() => {}),
  apiRanking: () => request('GET', '/api/stats/api-ranking'),
};
