// 브라우저 안의 가짜 Backend. 경로·응답 형식은 docs/contracts/api.md 를 따른다.
import insights from './generated/game_insights.json';
import specTrust from './generated/spec_trust.json';
import {
  GAMES, GENRES, TAGS, STORES, NOW, byId, currentPrices, saleEvents, KEYWORDS, SPEC_TEMPLATE,
  TRENDING, API_RANKING, REVIEW_SNIPPETS, historySeries,
} from './data.js';

const KEY = 'gamenuri_mock_state';
const defaults = () => ({
  user: null, wishlist: [], alerts: [], alert_logs: [], recent: [],
  specs: null, steam_id: null, notifications: { email_enabled: true },
  events: [],
});
let state = defaults();
try { state = { ...defaults(), ...JSON.parse(localStorage.getItem(KEY) || '{}') }; } catch { /* 무시 */ }
const save = () => { try { localStorage.setItem(KEY, JSON.stringify(state)); } catch { /* 무시 */ } };

class ApiError extends Error {
  constructor(status, code, message) { super(message); this.status = status; this.code = code; }
}
const need = () => { if (!state.user) throw new ApiError(401, 'UNAUTHORIZED', '로그인이 필요합니다'); };
const game = (id) => {
  const g = byId(id);
  if (!g) throw new ApiError(404, 'NOT_FOUND', '게임을 찾을 수 없습니다');
  return g;
};
const page = (list, q) => {
  const p = Number(q.page || 1), size = Number(q.size || 20);
  return { items: list.slice((p - 1) * size, p * size), total: list.length, page: p, size };
};
const today = (g) => g.history[g.history.length - 1];
const lowestOf = (g) => g.history.reduce((m, h) => (h.price_krw < m.price_krw ? h : m), g.history[0]);

// 목록·카드용 요약
function card(g) {
  const t = today(g);
  return {
    game_id: g.game_id, name: g.name, name_en: g.name_en, genres: g.genres, platforms: g.platforms,
    cover_url: g.cover_url, price_krw: t.price_krw, regular_krw: g.regular_krw, discount_pct: t.discount_pct || null,
    positive_ratio: g.positive_ratio, concurrent_players: g.concurrent_players,
    time_to_beat_hours: g.time_to_beat_hours, critic_score: critic(g).score, wished: state.wishlist.includes(g.game_id),
  };
}

// 목: 실제 Backend와 같은 모양. IGDB 평론가 점수(0~100)와 클리어 시간 3종(소수 첫째 자리).
function critic(g) {
  if (g.game_id % 9 === 0) return { score: null, count: null }; // 점수 없는 게임도 있다
  return { score: 62 + ((g.game_id * 7) % 34), count: 8 + ((g.game_id * 13) % 60) };
}
function timeToBeat(g) {
  const n = g.time_to_beat_hours;
  if (n == null) return null;
  const r1 = (x) => Math.round(x * 10) / 10;
  return { hastily_hours: r1(n * 0.7), normally_hours: r1(n), completely_hours: r1(n * 1.8), count: 100 + ((g.game_id * 37) % 900) };
}
// api.md: length 구간은 '보통' 클리어 시간 기준. short ≤10h, medium ≤40h, long 그 초과(없으면 제외)
const lengthOf = (h) => (h == null ? null : h <= 10 ? 'short' : h <= 40 ? 'medium' : 'long');

// 기준 이력은 PC·새 상품. PC가 없으면(콘솔 전용) 판단할 수 없다 (api.md '구매 타이밍').
const noPcHistory = (g) => !g.platforms.includes('PC');
function timing(g) {
  if (noPcHistory(g)) {
    return {
      game_id: g.game_id, verdict: 'insufficient_data', reason: '가격 이력이 부족해 판단하기 어려워요.',
      current_krw: null, lowest_krw: null, lowest_date: null, vs_lowest_pct: null, sale_count_2y: null,
    };
  }
  const t = today(g), low = lowestOf(g), ev = saleEvents(g.history);
  const pred = prediction(g);
  const nearLow = t.price_krw <= low.price_krw * 1.05;
  let verdict, reason;
  if (t.discount_pct >= 30 && nearLow) { verdict = 'buy_now'; reason = '역대 최저가에 가까운 가격이에요. 지금 사도 손해가 적어요.'; }
  else if (t.discount_pct >= 10) { verdict = 'neutral'; reason = `할인 중이지만 역대 최저가(${low.price_krw.toLocaleString('ko-KR')}원)보다는 높아요. 급하지 않다면 더 기다려도 좋아요.`; }
  else { verdict = 'wait'; reason = `정가에 가까워요. 다음 할인은 ${pred.next_sale_expected} 전후로 예상돼요.`; }
  return {
    game_id: g.game_id, verdict, reason, current_krw: t.price_krw, lowest_krw: low.price_krw,
    lowest_date: low.date, vs_lowest_pct: Math.round((t.price_krw / low.price_krw - 1) * 100),
    sale_count_2y: ev.length,
  };
}

function prediction(g) {
  const ev = saleEvents(g.history);
  if (noPcHistory(g) || ev.length < 2) {
    return {
      game_id: g.game_id, avg_sale_interval_days: null, next_sale_expected: null, expected_discount_pct: null,
      confidence: 'insufficient_data', basis: '가격 이력이 부족해 예측하기 어려워요.',
    };
  }
  const starts = ev.map((e) => new Date(e.start).getTime());
  const gaps = starts.slice(1).map((s, i) => (s - starts[i]) / 86400000);
  const avg = gaps.length ? Math.round(gaps.reduce((a, b) => a + b, 0) / gaps.length) : 60;
  const last = starts[starts.length - 1];
  let next = new Date(last + avg * 86400000);
  if (next < NOW) next = new Date(NOW.getTime() + 14 * 86400000);
  const avgPct = ev.length ? Math.round(ev.reduce((a, e) => a + e.max, 0) / ev.length) : 30;
  return {
    game_id: g.game_id, avg_sale_interval_days: avg, next_sale_expected: next.toISOString().slice(0, 10),
    expected_discount_pct: avgPct, confidence: ev.length >= 8 ? 'high' : ev.length >= 4 ? 'medium' : 'low',
    basis: `최근 2년 할인 ${ev.length}회 기준`,
  };
}

function reviews(g) {
  const kw = KEYWORDS[g.game_id] || KEYWORDS.default;
  const out = [];
  for (let i = 0; i < 14; i++) {
    const rec = i % 5 !== 4 && (i / 14 < g.positive_ratio + 0.05);
    const list = rec ? kw.pros : kw.cons;
    const k = list[i % list.length];
    const tpl = REVIEW_SNIPPETS[rec ? 'pos' : 'neg'];
    out.push({
      review_id: `${g.game_id}-${i}`, source: i % 6 === 5 ? 'danawa' : 'steam', recommended: rec,
      text: tpl[i % tpl.length].replace('{k}', k), playtime_hours: 5 + ((i * 37) % 180),
      created_at: new Date(NOW.getTime() - i * 5 * 86400000).toISOString(),
    });
  }
  return out;
}

function spec_check(g) {
  const s = state.specs;
  if (!s || (!s.cpu && !s.gpu && !s.ram_gb)) throw new ApiError(400, 'SPEC_REQUIRED', '마이페이지에서 PC 사양을 먼저 입력해 주세요');
  const score = (/rtx\s?(30|40|50)|rx\s?(6|7)\d{3}/i.test(s.gpu || '') ? 2 : /gtx\s?(10|16)|rx\s?5/i.test(s.gpu || '') ? 1 : 0)
    + (Number(s.ram_gb) >= 16 ? 1 : 0);
  const verdict = score >= 3 ? 'rec_ok' : score >= 1 ? 'min_ok' : 'below_min';
  const reason = {
    rec_ok: '권장 사양을 충족해요. 높은 옵션으로 즐길 수 있어요.',
    min_ok: 'GPU가 권장보다 낮아 옵션을 낮춰야 해요.',
    below_min: '최소 사양에 못 미칠 수 있어요. 구매 전 환불 정책을 확인하세요.',
  }[verdict];
  return { game_id: g.game_id, verdict, reason, generated_by: 'ai', cached: true };
}

const norm = (s) => s.toLowerCase().replace(/\s+/g, '');
function search(q) {
  let list = GAMES;
  if (q.q) {
    const k = norm(q.q);
    list = list.filter((g) => norm(g.name).includes(k) || norm(g.name_en).includes(k));
  }
  if (q.platform) list = list.filter((g) => g.platforms.includes(q.platform));
  if (q.genre) list = list.filter((g) => g.genres.includes(q.genre));
  if (q.tag) list = list.filter((g) => g.tags.includes(q.tag));
  if (q.length) list = list.filter((g) => lengthOf(g.time_to_beat_hours) === q.length);
  if (q.sort === 'rating') list = [...list].sort((a, b) => (critic(b).score ?? -1) - (critic(a).score ?? -1) || (critic(b).count ?? 0) - (critic(a).count ?? 0));
  if (q.sort === 'price') list = [...list].sort((a, b) => today(a).price_krw - today(b).price_krw);
  if (q.sort === 'popular') list = [...list].sort((a, b) => b.concurrent_players - a.concurrent_players || b.positive_ratio - a.positive_ratio);
  if (q.sort === 'discount') list = [...list].sort((a, b) => (today(b).discount_pct || 0) - (today(a).discount_pct || 0));
  return list;
}

// [메서드, 경로 정규식, 핸들러(match, query, body)]
const routes = [
  ['GET', /^\/api\/health$/, () => ({ status: 'ok' })],

  // 인증 (구글 로그인은 모의 계정으로 대체)
  ['POST', /^\/api\/auth\/mock-login$/, () => {
    state.user = { user_id: 1, email: 'gamer@example.com', name: '겜누리 사용자' };
    save(); return state.user;
  }],
  ['POST', /^\/api\/auth\/logout$/, () => { state.user = null; save(); return { ok: true }; }],
  ['POST', /^\/api\/auth\/refresh$/, () => { need(); return { ok: true }; }],
  ['GET', /^\/api\/me$/, () => { need(); return { ...state.user, steam_id: state.steam_id }; }],
  ['PATCH', /^\/api\/me$/, (m, q, b) => { need(); state.user = { ...state.user, ...b }; save(); return state.user; }],
  ['PUT', /^\/api\/me\/steam$/, (m, q, b) => {
    need();
    if (!/^\d{17}$/.test(b.steam_id || '')) throw new ApiError(400, 'INVALID_STEAM_ID', 'Steam ID는 17자리 숫자예요');
    state.steam_id = b.steam_id; save(); return { steam_id: b.steam_id, owned_games: 126 };
  }],

  // 게임
  ['GET', /^\/api\/games$/, (m, q) => { const l = search(q); return { ...page(l.map(card), q) }; }],
  ['GET', /^\/api\/games\/autocomplete$/, (m, q) => ({
    items: search({ q: q.q || '' }).slice(0, 6).map((g) => ({ game_id: g.game_id, name: g.name, name_en: g.name_en })),
  })],
  ['GET', /^\/api\/games\/popular$/, () => ({ items: [...GAMES].sort((a, b) => b.concurrent_players - a.concurrent_players || b.positive_ratio - a.positive_ratio).slice(0, 8).map(card) })],
  ['GET', /^\/api\/games\/deals$/, () => ({
    // 할인 중 = 새 상품 최저가의 discount_pct > 0, 할인율 큰 순. 로그인 없이 보는 목록이라 wished는 항상 false.
    items: GAMES.filter((g) => today(g).discount_pct > 0).sort((a, b) => today(b).discount_pct - today(a).discount_pct)
      .slice(0, 20).map((g) => ({ ...card(g), wished: false })),
  })],
  ['GET', /^\/api\/games\/short$/, () => ({ items: [...GAMES].filter((g) => g.time_to_beat_hours <= 10).sort((a, b) => a.time_to_beat_hours - b.time_to_beat_hours).map(card) })],
  ['GET', /^\/api\/games\/players\/top$/, () => ({
    items: [...GAMES].filter((g) => g.concurrent_players > 0).sort((a, b) => b.concurrent_players - a.concurrent_players).slice(0, 6).map(card),
  })],
  ['GET', /^\/api\/games\/players\/low$/, () => ({
    items: GAMES.filter((g) => g.online_only && g.concurrent_players < 1000).sort((a, b) => a.concurrent_players - b.concurrent_players).map((g) => ({ ...card(g), warning: '접속자가 적어 매칭이 어려울 수 있어요' })),
  })],
  ['GET', /^\/api\/genres$/, () => ({ items: GENRES })],
  ['GET', /^\/api\/tags$/, () => ({ items: TAGS })],
  ['GET', /^\/api\/exchange-rates$/, () => ({ base: 'KRW', rates: { USD: 1385.2, EUR: 1502.8, GBP: 1760.4 }, updated_at: '2026-11-21T00:00:00Z' })],

  ['GET', /^\/api\/games\/(\d+)$/, (m) => {
    const g = game(m[1]);
    const { history, ...rest } = g;
    // insights: analysis/ 파이썬 분석이 만든 게임별 태그 (B). 실제로는 Backend가 같은 모양으로 내려준다.
    return { ...rest, ...card(g), lowest_krw: lowestOf(g).price_krw, time_to_beat: timeToBeat(g), critic_count: critic(g).count, insights: insights.items[String(g.game_id)] || [] };
  }],
  ['GET', /^\/api\/games\/(\d+)\/prices$/, (m) => {
    const g = game(m[1]); const items = currentPrices(g);
    // lowest = 새 상품 최저가 (api.md '현재가' 정의). 새 상품이 없으면 null.
    const news = items.filter((i) => i.item_condition === 'new');
    const low = news.reduce((a, b) => (!a || b.price_krw < a.price_krw ? b : a), null);
    return {
      game_id: g.game_id, items,
      lowest: low && { store: low.store, edition: low.edition, platform: low.platform, item_condition: low.item_condition, price_krw: low.price_krw },
    };
  }],
  ['GET', /^\/api\/games\/(\d+)\/history$/, (m, q) => {
    const g = game(m[1]); const days = Number(q.days || 180);
    // 필터를 안 주면 모든 시리즈를 합쳐 준다 (실제 Backend와 같게).
    const platform = q.platform || null, item_condition = q.item_condition || null;
    const combos = g.platforms.flatMap((p) => ['new', 'used'].filter((c) => !(p === 'PC' && c === 'used')).map((c) => [p, c]))
      .filter(([p, c]) => (!platform || p === platform) && (!item_condition || c === item_condition));
    const items = combos.flatMap(([p, c]) => historySeries(g, p, c).slice(-days));
    return { game_id: g.game_id, days, platform, item_condition, items };
  }],
  ['GET', /^\/api\/games\/(\d+)\/lowest$/, (m) => {
    // platform·item_condition별 역대 최저가 (콘솔은 수집 이후 최저가)
    const g = game(m[1]);
    const items = g.platforms.flatMap((p) => ['new', 'used'].filter((c) => !(p === 'PC' && c === 'used')).map((c) => {
      const ser = historySeries(g, p, c);
      const l = ser.reduce((a, b) => (b.price_krw < a.price_krw ? b : a), ser[0]);
      return { platform: p, item_condition: c, store: l.store, edition: l.edition, price_krw: l.price_krw, regular_krw: l.regular_krw, discount_pct: l.discount_pct, date: l.collected_at.slice(0, 10) };
    }));
    return { game_id: g.game_id, items };
  }],
  ['GET', /^\/api\/games\/(\d+)\/timing$/, (m) => timing(game(m[1]))],
  ['GET', /^\/api\/games\/(\d+)\/prediction$/, (m) => prediction(game(m[1]))],
  ['GET', /^\/api\/games\/(\d+)\/reviews$/, (m, q) => page(reviews(game(m[1])), { size: 10, ...q })],
  ['GET', /^\/api\/games\/(\d+)\/reviews\/summary$/, (m) => {
    const g = game(m[1]); const kw = KEYWORDS[g.game_id] || KEYWORDS.default;
    return {
      game_id: g.game_id, positive_ratio: g.positive_ratio,
      summary: `${kw.pros.slice(0, 2).join('·')}이(가) 특히 호평받고, ${kw.cons[0]} 쪽은 아쉽다는 의견이 있어요.`,
      pros: kw.pros, cons: kw.cons, generated_by: 'ai', updated_at: '2026-11-20T18:00:00Z',
    };
  }],
  ['GET', /^\/api\/reviews\/search$/, (m, q) => {
    const k = norm(q.q || '');
    const items = GAMES.flatMap((g) => reviews(g).map((r) => ({ ...r, game_id: g.game_id, game_name: g.name })))
      .filter((r) => !k || norm(r.text).includes(k));
    return page(items, q);
  }],
  // trust: analysis/ 파이썬이 리뷰 키워드로 계산한 사양표 신뢰도 (B). 실제로는 Backend가 같은 모양으로 내려준다.
  ['GET', /^\/api\/games\/(\d+)\/requirements$/, (m) => ({ ...SPEC_TEMPLATE(game(m[1])), trust: specTrust.items[String(m[1])] || null })],
  ['GET', /^\/api\/games\/(\d+)\/spec-check$/, (m) => { need(); return spec_check(game(m[1])); }],

  // 내 정보: 찜·알림·사양
  ['GET', /^\/api\/me\/wishlist$/, () => { need(); return { items: state.wishlist.map((id) => card(byId(id))), total: state.wishlist.length }; }],
  ['POST', /^\/api\/me\/wishlist$/, (m, q, b) => {
    need(); game(b.game_id);
    if (!state.wishlist.includes(b.game_id)) state.wishlist.push(b.game_id);
    save(); return { game_id: b.game_id, wished: true };
  }],
  ['DELETE', /^\/api\/me\/wishlist$/, (m, q) => {
    need(); state.wishlist = state.wishlist.filter((id) => id !== Number(q.game_id)); save();
    return { game_id: Number(q.game_id), wished: false };
  }],
  ['GET', /^\/api\/me\/alerts$/, () => {
    need();
    return { items: state.alerts.map((a) => ({ ...a, game_name: byId(a.game_id).name, current_krw: today(byId(a.game_id)).price_krw })), total: state.alerts.length };
  }],
  ['POST', /^\/api\/me\/alerts$/, (m, q, b) => {
    need(); const g = game(b.game_id);
    if (!(b.target_price_krw > 0)) throw new ApiError(400, 'INVALID_PRICE', '목표가를 입력해 주세요');
    const a = { alert_id: Date.now(), game_id: g.game_id, target_price_krw: Number(b.target_price_krw), active: true, created_at: NOW.toISOString() };
    state.alerts = [...state.alerts.filter((x) => x.game_id !== g.game_id), a];
    if (a.target_price_krw >= today(g).price_krw) {
      state.alert_logs.unshift({ log_id: Date.now(), game_id: g.game_id, game_name: g.name, price_krw: today(g).price_krw, target_price_krw: a.target_price_krw, sent_at: NOW.toISOString(), channel: 'email' });
    }
    save(); return a;
  }],
  ['PATCH', /^\/api\/me\/alerts\/(\d+)$/, (m, q, b) => {
    need(); const a = state.alerts.find((x) => x.alert_id === Number(m[1]));
    if (!a) throw new ApiError(404, 'NOT_FOUND', '알림을 찾을 수 없습니다');
    if ('target_price_krw' in b && !(b.target_price_krw > 0)) throw new ApiError(400, 'INVALID_PRICE', '목표가를 입력해 주세요');
    Object.assign(a, b); save(); return a;
  }],
  ['DELETE', /^\/api\/me\/alerts\/(\d+)$/, (m) => {
    need(); state.alerts = state.alerts.filter((x) => x.alert_id !== Number(m[1])); save(); return { ok: true };
  }],
  ['GET', /^\/api\/me\/alerts\/logs$/, () => { need(); return { items: state.alert_logs, total: state.alert_logs.length }; }],
  ['GET', /^\/api\/me\/notifications$/, () => { need(); return state.notifications; }],
  ['PUT', /^\/api\/me\/notifications$/, (m, q, b) => { need(); state.notifications = { email_enabled: !!b.email_enabled }; save(); return state.notifications; }],
  ['GET', /^\/api\/me\/specs$/, () => { need(); return state.specs || { os: '', cpu: '', gpu: '', ram_gb: null }; }],
  ['PUT', /^\/api\/me\/specs$/, (m, q, b) => { need(); state.specs = { os: b.os || '', cpu: b.cpu || '', gpu: b.gpu || '', ram_gb: b.ram_gb ? Number(b.ram_gb) : null }; save(); return state.specs; }],

  // 추천
  ['GET', /^\/api\/me\/taste$/, () => {
    need();
    if (!state.steam_id) throw new ApiError(400, 'STEAM_REQUIRED', 'Steam ID를 먼저 연동해 주세요');
    return {
      total_playtime_hours: 1840, owned_games: 126,
      top_genres: [{ genre: '액션', pct: 38 }, { genre: 'RPG', pct: 27 }, { genre: '인디', pct: 18 }, { genre: '시뮬레이션', pct: 10 }, { genre: '전략', pct: 7 }],
      style: '긴 호흡의 액션·RPG를 즐기는 탐험가형',
      preferred_length: 'medium',
    };
  }],
  ['GET', /^\/api\/me\/recommendations$/, () => {
    need();
    if (!state.steam_id) throw new ApiError(400, 'STEAM_REQUIRED', 'Steam ID를 먼저 연동해 주세요');
    const picks = [GAMES[2], GAMES[7], GAMES[8], GAMES[6]];
    return { items: picks.map((g, i) => ({ ...card(g), reason: ['RPG 장르를 많이 플레이했어요', '액션 장르를 많이 플레이했어요', '어드벤처 장르를 많이 플레이했어요', '시뮬레이션 장르를 많이 플레이했어요'][i] })) };
  }],

  // 검색·운영
  ['GET', /^\/api\/search\/trending$/, () => ({ window: '1h', items: TRENDING })],
  ['GET', /^\/api\/search\/recent$/, () => { need(); return { items: state.recent }; }],
  ['POST', /^\/api\/events$/, (m, q, b) => {
    if (b?.type === 'search' && b.query && state.user) { state.recent = [b.query, ...state.recent.filter((x) => x !== b.query)].slice(0, 8); save(); }
    console.debug('[clickstream→Kafka(mock)]', b);
    return { accepted: true };
  }],
  ['GET', /^\/api\/stats\/api-ranking$/, () => ({ items: API_RANKING })],
];

export async function mockFetch(method, url, body) {
  await new Promise((r) => setTimeout(r, 120 + Math.random() * 180));
  const u = new URL(url, 'http://mock');
  const query = Object.fromEntries(u.searchParams);
  for (const [mt, re, fn] of routes) {
    const m = u.pathname.match(re);
    if (mt === method && m) {
      try { return fn(m, query, body); } catch (e) {
        if (e instanceof ApiError) throw e;
        throw new ApiError(500, 'INTERNAL', String(e.message || e));
      }
    }
  }
  throw new ApiError(404, 'NOT_FOUND', `목 API에 없는 경로: ${method} ${u.pathname}`);
}

export { STORES };
