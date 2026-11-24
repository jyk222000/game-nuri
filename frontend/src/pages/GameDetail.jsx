import { useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { api } from '../api/client.js';
import { useAuth } from '../auth.jsx';
import { useAsync } from '../lib/useAsync.js';
import { State, Section, cover } from '../components/ui.jsx';
import { byKey } from './analysis/meta.js';
import PriceChart from '../components/PriceChart.jsx';
import { won, dateKST, dateTimeKST, platformName, storeName, editionLabel, CONDITION } from '../lib/format.js';

const VERDICT = {
  buy_now: { label: '지금 사세요', cls: 'ok' },
  neutral: { label: '조금 더 기다려도 좋아요', cls: 'mid' },
  wait: { label: '기다리세요', cls: 'bad' },
  insufficient_data: { label: '판단할 데이터가 부족해요', cls: 'mid' },
};
const SPEC_VERDICT = {
  rec_ok: { label: '권장 사양 충족', cls: 'ok' },
  min_ok: { label: '최소 사양 충족', cls: 'mid' },
  below_min: { label: '최소 사양 미달', cls: 'bad' },
};

export default function GameDetail() {
  const { id } = useParams();
  const { user } = useAuth();
  const game = useAsync(() => api.game(id), [id]);
  // 상세 응답의 wished는 항상 false(공개 API)라서, 로그인했으면 찜 목록으로 직접 확인한다.
  const wl = useAsync(() => (user ? api.wishlist() : Promise.resolve(null)), [user]);
  const wished = !!wl.data?.items.some((x) => x.game_id === Number(id));

  useEffect(() => { api.event('view_game', { game_id: Number(id) }); }, [id]);

  return (
    <State s={game}>
      {(g) => (
        <>
          <Head key={String(wished)} g={g} user={user} wished0={wished} />
          <LowPlayersBanner id={g.game_id} />
          <div className="two">
            <div>
              <Timing id={id} />
              <Prices id={id} />
              <Lowest id={id} />
              <History id={id} user={user} platforms={g.platforms} />
            </div>
            <aside>
              <AlertBox g={g} user={user} />
              <ReviewSummary id={id} />
              <Requirements id={id} user={user} />
            </aside>
          </div>
          <Reviews id={id} />
        </>
      )}
    </State>
  );
}

// 접속자가 적은 온라인 게임(#33 players/low 목록에 있는 게임)이면 경고를 띄운다.
function LowPlayersBanner({ id }) {
  const s = useAsync(() => api.playersLow(), []);
  const hit = s.data?.items.find((x) => x.game_id === Number(id));
  if (!hit) return null;
  return (
    <div className="low-banner" role="alert">
      <b>⚠ 접속자가 적은 온라인 게임이에요</b>
      <span>{hit.warning || '접속자가 적어 매칭이 어려울 수 있어요'}. 구매 전에 한 번 더 확인해 보세요.</span>
    </div>
  );
}

function Head({ g, user, wished0 }) {
  const [wished, setWished] = useState(wished0);
  const toggle = async () => {
    if (!user) return alert('로그인 후 찜할 수 있어요.');
    if (wished) await api.unwish(g.game_id); else await api.wish(g.game_id);
    setWished(!wished);
  };
  return (
    <section className="detail-h">
      <div className={`big-cover${g.cover_url ? ' has-img' : ''}`} style={cover(g)}>{!g.cover_url && <span>{g.name}</span>}</div>
      <div>
        <h1>{g.name}</h1>
        <p className="muted">{g.name_en} · 출시 {dateKST(g.release_date)}</p>
        <div className="chips">
          {g.platforms.map((p) => <i key={p}>{platformName(p)}</i>)}
          {g.genres.map((x) => <i key={x} className="g">{x}</i>)}
        </div>
        <p>{g.summary}</p>
        <ul className="facts">
          {g.positive_ratio != null && <li><b>{Math.round(g.positive_ratio * 100)}%</b> 긍정 리뷰</li>}
          {g.time_to_beat_hours != null && <li><b>{g.time_to_beat_hours}시간</b> 클리어(IGDB)</li>}
          {g.concurrent_players != null && g.concurrent_players > 0 && <li><b>{g.concurrent_players.toLocaleString('ko-KR')}</b> 명 접속 중</li>}
        </ul>
        {g.insights?.length > 0 && (
          <ul className="insights" aria-label="분석 태그">
            {g.insights.map((t) => (
              <li key={t.code}>
                {byKey(t.analysis)
                  ? <Link to={`/analysis/${t.analysis}`} className={`pill tone-${t.tone}`}>{t.label}</Link>
                  : <span className={`pill tone-${t.tone}`}>{t.label}</span>}
                <small className="muted">{t.detail}</small>
              </li>
            ))}
          </ul>
        )}
        <button className={wished ? 'btn on' : 'btn'} onClick={toggle}>{wished ? '♥ 찜함' : '♡ 찜하기'}</button>
      </div>
    </section>
  );
}

function Timing({ id }) {
  const t = useAsync(() => api.timing(id), [id]);
  const p = useAsync(() => api.prediction(id), [id]);
  return (
    <Section title="구매 타이밍">
      <State s={t}>
        {(d) => (
          <div className={`verdict ${VERDICT[d.verdict].cls}`}>
            <strong>{VERDICT[d.verdict].label}</strong>
            <p>{d.reason}</p>
            {d.verdict !== 'insufficient_data' && (
              <small>
                PC 새 상품 기준 현재 {won(d.current_krw)} · 역대 최저 {won(d.lowest_krw)} ({dateKST(d.lowest_date)}) ·
                최저가 대비 {d.vs_lowest_pct > 0 ? '+' : ''}{d.vs_lowest_pct}%
              </small>
            )}
          </div>
        )}
      </State>
      <State s={p}>
        {(d) => (
          d.confidence === 'insufficient_data' ? (
            <p className="muted">할인 예측: {d.basis}</p>
          ) : (
            <div className="predict">
              <span>📅 다음 할인 예상 <b>{dateKST(d.next_sale_expected)}</b></span>
              <span>예상 할인율 <b>{d.expected_discount_pct}%</b></span>
              <span>평균 {d.avg_sale_interval_days}일 간격</span>
              <small className="muted">{d.basis} · 신뢰도 {{ low: '낮음', medium: '보통', high: '높음' }[d.confidence]}</small>
            </div>
          )
        )}
      </State>
    </Section>
  );
}

// 원화 환산 기준 환율 (#14). 응답은 USD·EUR·GBP, 1단위당 원.
function Rates() {
  const r = useAsync(() => api.exchangeRates(), []);
  if (!r.data) return null;
  const txt = Object.entries(r.data.rates).map(([c, v]) => `1 ${c} = ${Math.round(v).toLocaleString('ko-KR')}원`).join(' · ');
  return <span>({txt}{r.data.updated_at && `, ${dateKST(r.data.updated_at)} 기준`})</span>;
}

// 플랫폼·상태별 역대 최저가 (#12). 콘솔은 다나와를 수집하기 시작한 뒤의 최저가다.
function Lowest({ id }) {
  const s = useAsync(() => api.lowest(id), [id]);
  return (
    <Section title="역대 최저가">
      <State s={s} isEmpty={(d) => !d.items.length} emptyMsg="아직 모인 가격이 없어요.">
        {(d) => (
          <>
            <table className="tbl"><tbody>
              {d.items.map((i) => (
                <tr key={i.platform + i.item_condition}>
                  <td>{platformName(i.platform)} · {CONDITION[i.item_condition]}</td>
                  <td>{storeName(i.store)} · {editionLabel(i)}</td>
                  <td className="num"><b>{won(i.price_krw)}</b> {i.discount_pct > 0 && <em className="badge s">-{i.discount_pct}%</em>}</td>
                  <td className="muted">{dateKST(i.date)}{i.platform !== 'PC' && ' (수집 이후)'}</td>
                </tr>
              ))}
            </tbody></table>
          </>
        )}
      </State>
    </Section>
  );
}

function Prices({ id }) {
  const s = useAsync(() => api.prices(id), [id]);
  return (
    <Section title="스토어별 가격 비교">
      <State s={s} isEmpty={(d) => !d.items.length}>
        {(d) => {
          const sorted = [...d.items].sort((a, b) => a.price_krw - b.price_krw);
          const pc = sorted.filter((i) => i.platform === 'PC');
          const con = sorted.filter((i) => i.platform !== 'PC');
          // 최저가 표시는 서버가 알려 준 새 상품 최저가(lowest)와 같은 행에만 붙인다.
          const L = d.lowest;
          const Row = ({ i }) => {
            const best = !!L && ['store', 'edition', 'platform', 'item_condition'].every((k) => i[k] === L[k]);
            return (
              <tr className={best ? 'best' : ''}>
                <td>{storeName(i.store)}{i.platform !== 'PC' && ` · ${platformName(i.platform)}`}</td>
                <td>{editionLabel(i)}</td>
                <td className="num">{i.discount_pct > 0 && <s>{won(i.regular_krw)}</s>} <b>{won(i.price_krw)}</b></td>
                <td>{i.discount_pct > 0 ? <em className="badge s">-{i.discount_pct}%</em> : ''}{best && <em className="badge low">최저가</em>}</td>
                <td><a href={i.url || '#'} onClick={() => api.event('click_store', { game_id: Number(id), store: i.store })}>구매 →</a></td>
              </tr>
            );
          };
          return (
            <>
              {pc.length > 0 && <><h3>PC 스토어</h3><table className="tbl"><tbody>{pc.map((i) => <Row key={[i.store, i.edition, i.platform, i.item_condition].join()} i={i} />)}</tbody></table></>}
              {con.length > 0 && <><h3>콘솔 (다나와 · 새 상품·중고)</h3><table className="tbl"><tbody>{con.map((i) => <Row key={[i.store, i.edition, i.platform, i.item_condition].join()} i={i} />)}</tbody></table></>}
              <small className="muted">수집 {dateTimeKST(d.items[0].collected_at)} · 원화 환산 기준 <Rates /></small>
            </>
          );
        }}
      </State>
    </Section>
  );
}

// 가격 이력은 "가격이 바뀐 날"만 기록된다. 바뀌지 않은 날은 스토어별 직전 가격을 이어서 채운 뒤,
// 하루에 점 하나 = 그날 모든 스토어 중 가장 싼 값으로 만든다. 마지막 날은 오늘(UTC)까지 이어 붙인다.
// 전체 이력으로 계산한 다음 마지막 `days`일만 잘라 쓴다(기간 안에 안 바뀐 스토어도 빠지지 않게).
const DAY_MS = 86400000;
const isoDay = (t) => new Date(t).toISOString().slice(0, 10);
function dailySeries(items, days) {
  if (!items.length) return [];
  const rows = [...items].sort((a, b) => (a.collected_at < b.collected_at ? -1 : 1));
  const byDay = new Map();
  for (const r of rows) {
    const d = r.collected_at.slice(0, 10);
    if (!byDay.has(d)) byDay.set(d, []);
    byDay.get(d).push(r);
  }
  const first = Date.parse(`${rows[0].collected_at.slice(0, 10)}T00:00:00Z`);
  const today = Date.parse(`${isoDay(Date.now())}T00:00:00Z`);
  const last = Math.max(today, Date.parse(`${rows[rows.length - 1].collected_at.slice(0, 10)}T00:00:00Z`));
  const since = isoDay(last - days * DAY_MS);
  const state = new Map(); // 스토어·에디션별 현재 가격
  const out = [];
  for (let t = first; t <= last; t += DAY_MS) {
    const date = isoDay(t);
    for (const r of byDay.get(date) || []) state.set(`${r.store}|${r.edition}`, r); // 같은 날 여러 번이면 마지막 값
    if (date < since) continue;
    let best = null;
    for (const r of state.values()) if (!best || r.price_krw < best.price_krw) best = r;
    if (best) out.push({ date, price_krw: best.price_krw, regular_krw: best.regular_krw, discount_pct: best.discount_pct });
  }
  return out;
}

function History({ id, user, platforms }) {
  const [days, setDays] = useState(180);
  const [platform, setPlatform] = useState(platforms.includes('PC') ? 'PC' : platforms[0]);
  const [cond, setCond] = useState('new');
  const itemCondition = platform === 'PC' ? 'new' : cond; // PC는 새 상품(스토어)만 모은다
  // 모든 플랫폼·상태의 전체 이력을 한 번 받아 두고, 탭(플랫폼·새 상품/중고·기간)은 화면에서 고른다. 탭을 눌러도 다시 받지 않는다.
  const h = useAsync(() => api.history(id, 3650), [id]);
  const all = h.data?.items;
  const mine = useMemo(() => (all || []).filter((r) => r.platform === platform && r.item_condition === itemCondition), [all, platform, itemCondition]);
  // 세로축 범위는 이 게임의 모든 탭(플랫폼·새 상품/중고)을 합친 값으로 고정한다. 탭을 오가도 같은 가격이 같은 높이로 보이게.
  const domain = useMemo(() => {
    const groups = new Map();
    for (const r of all || []) {
      const k = `${r.platform}|${r.item_condition}`;
      if (!groups.has(k)) groups.set(k, []);
      groups.get(k).push(r);
    }
    let lo = Infinity, hi = -Infinity;
    for (const g of groups.values()) for (const pt of dailySeries(g, days)) { lo = Math.min(lo, pt.price_krw); hi = Math.max(hi, pt.price_krw); }
    return Number.isFinite(lo) ? [lo, hi] : null;
  }, [all, days]);
  const alerts = useAsync(() => (user ? api.alerts() : Promise.resolve({ items: [] })), [id, user]);
  const target = alerts.data?.items.find((a) => a.game_id === Number(id))?.target_price_krw;
  return (
    <Section title="가격 이력">
      <div className="hist-ctl">
        {platforms.length > 1 && (
          <div className="seg" role="group" aria-label="플랫폼">
            {platforms.map((p) => <button key={p} className={p === platform ? 'on' : ''} onClick={() => setPlatform(p)}>{platformName(p)}</button>)}
          </div>
        )}
        {/* PC는 새 상품만 있다. 탭이 나타났다 사라지며 화면이 밀리지 않게 자리는 항상 잡아 두고 PC일 때만 숨긴다. */}
        <div className="seg" role="group" aria-label="상품 상태" style={platform === 'PC' ? { visibility: 'hidden' } : undefined} aria-hidden={platform === 'PC'}>
          {['new', 'used'].map((c) => <button key={c} tabIndex={platform === 'PC' ? -1 : 0} className={c === cond ? 'on' : ''} onClick={() => setCond(c)}>{CONDITION[c]}</button>)}
        </div>
        <div className="seg" role="group" aria-label="기간">
          {[30, 90, 180, 365].map((d) => <button key={d} className={d === days ? 'on' : ''} onClick={() => setDays(d)}>{d}일</button>)}
        </div>
      </div>
      <State s={h} isEmpty={() => !mine.length} emptyMsg="아직 모인 가격 이력이 없어요.">
        {() => <PriceChart items={dailySeries(mine, days)} domain={domain} target={target} />}
      </State>
    </Section>
  );
}

function AlertBox({ g, user }) {
  const [price, setPrice] = useState('');
  const [msg, setMsg] = useState(null);
  const submit = async (e) => {
    e.preventDefault();
    try {
      await api.addAlert(g.game_id, Number(price));
      api.event('set_alert', { game_id: g.game_id });
      setMsg({ ok: true, t: `${won(Number(price))} 이하가 되면 메일로 알려드려요.` });
    } catch (err) { setMsg({ ok: false, t: err.message }); }
  };
  return (
    <Section title="🔔 목표가 알림">
      {user ? (
        <form className="form" onSubmit={submit}>
          <label>목표 가격(원)
            <input type="number" min="100" step="100" value={price} placeholder={String(Math.round(g.price_krw * 0.8 / 100) * 100)} onChange={(e) => setPrice(e.target.value)} required />
          </label>
          <button className="btn pri">알림 등록</button>
          {msg && <small className={msg.ok ? 'ok' : 'err'}>{msg.t}</small>}
        </form>
      ) : <p className="muted"><Link to="/login">로그인</Link>하면 목표가 도달 시 메일을 받을 수 있어요.</p>}
    </Section>
  );
}

function ReviewSummary({ id }) {
  const s = useAsync(() => api.reviewSummary(id), [id]);
  return (
    <Section title="리뷰 요약" right={<span className="tag-ai">AI 요약</span>}>
      <State s={s}>
        {(d) => (
          <>
            <div className="meter"><div style={{ width: `${d.positive_ratio * 100}%` }} /></div>
            <small className="muted">긍정 {Math.round(d.positive_ratio * 100)}%</small>
            <p>{d.summary}</p>
            <div className="kw"><span className="ok">👍</span>{d.pros.map((k) => <i key={k} className="pro">{k}</i>)}</div>
            <div className="kw"><span className="err">👎</span>{d.cons.map((k) => <i key={k} className="con">{k}</i>)}</div>
            <small className="muted">{dateTimeKST(d.updated_at)} 갱신 · 하루 1회 생성</small>
          </>
        )}
      </State>
    </Section>
  );
}

const TRUST = { good: ['신뢰할 만해요', 'ok'], caution: ['주의', 'mid'], bad: ['믿기 어려워요', 'bad'], hold: ['판단 보류', ''] };

// 리뷰 키워드(성능 문제 언급 비율)로 본 사양표 신뢰도. 계산은 analysis/ 파이썬, 여기서는 보여 주기만 한다.
function TrustBadge({ t }) {
  if (!t) return null;
  const [label, cls] = TRUST[t.verdict];
  return (
    <div className={`verdict trust ${cls}`}>
      <strong>사양표 신뢰도: {label}</strong>
      <p>{t.reason}</p>
      {t.keywords?.length > 0 && (
        <div className="kw"><span className="muted">많이 나온 말</span>{t.keywords.map((k) => <i key={k.keyword} className="con">{k.keyword} {k.share}%</i>)}</div>
      )}
      <small className="muted">리뷰 키워드로 본 참고 지표예요. 내 PC가 사양을 충족하는지는 반영하지 않아요.</small>
    </div>
  );
}

function Requirements({ id, user }) {
  const r = useAsync(() => api.requirements(id), [id]);
  const [check, setCheck] = useState(null);
  const run = async () => {
    try { setCheck({ data: await api.specCheck(id) }); } catch (e) { setCheck({ error: e }); }
  };
  return (
    <Section title="PC 사양">
      <State s={r}>
        {(d) => (
          <>
          <TrustBadge t={d.trust} />
          {/* game_requirements 텍스트 컬럼 그대로 (api.md). 구조화는 ⑥ 방식이 정해진 뒤. */}
          <h3>최소</h3><p className="spec-text">{d.minimum_text || '정보 없음'}</p>
          <h3>권장</h3><p className="spec-text">{d.recommended_text || '정보 없음'}</p>
          </>
        )}
      </State>
      {user ? (
        <>
          <button className="btn" onClick={run}>내 PC로 돌려도 될까?</button>
          {check?.data && (
            <div className={`verdict ${SPEC_VERDICT[check.data.verdict].cls}`}>
              <strong>{SPEC_VERDICT[check.data.verdict].label} <span className="tag-ai">AI 판정</span></strong>
              <p>{check.data.reason}</p>
            </div>
          )}
          {check?.error && <p className="err">{check.error.message} <Link to="/me">마이페이지로</Link></p>}
        </>
      ) : <p className="muted"><Link to="/login">로그인</Link> 후 내 PC 사양과 비교할 수 있어요.</p>}
    </Section>
  );
}

function Reviews({ id }) {
  const r = useAsync(() => api.reviews(id), [id]);
  return (
    <Section title="리뷰">
      <State s={r} isEmpty={(d) => !d.items.length}>
        {(d) => (
          <ul className="reviews">
            {d.items.map((v) => (
              <li key={v.review_id}>
                <span className={v.recommended ? 'ok' : 'err'}>{v.recommended ? '👍 추천' : '👎 비추천'}</span>
                <p>{v.text}</p>
                <small className="muted">{v.source === 'steam' ? 'Steam' : '다나와'} · 플레이 {v.playtime_hours}시간 · {dateKST(v.created_at)}</small>
              </li>
            ))}
          </ul>
        )}
      </State>
    </Section>
  );
}
