import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { api } from '../api/client.js';
import { useAuth } from '../auth.jsx';
import { useAsync } from '../lib/useAsync.js';
import { State, Section, cover } from '../components/ui.jsx';
import PriceChart from '../components/PriceChart.jsx';
import { won, dateKST, dateTimeKST, PLATFORM, STORE_NAME, EDITION } from '../lib/format.js';

const VERDICT = {
  buy_now: { label: '지금 사세요', cls: 'ok' },
  neutral: { label: '조금 더 기다려도 좋아요', cls: 'mid' },
  wait: { label: '기다리세요', cls: 'bad' },
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

  useEffect(() => { api.event('view_game', { game_id: Number(id) }); }, [id]);

  return (
    <State s={game}>
      {(g) => (
        <>
          <Head g={g} user={user} />
          <div className="two">
            <div>
              <Timing id={id} />
              <Prices id={id} />
              <History id={id} user={user} />
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

function Head({ g, user }) {
  const [wished, setWished] = useState(g.wished);
  const toggle = async () => {
    if (!user) return alert('로그인 후 찜할 수 있어요.');
    if (wished) await api.unwish(g.game_id); else await api.wish(g.game_id);
    setWished(!wished);
  };
  return (
    <section className="detail-h">
      <div className="big-cover" style={cover(g.hue)}><span>{g.name}</span></div>
      <div>
        <h1>{g.name}</h1>
        <p className="muted">{g.name_en} · 출시 {dateKST(g.release_date)}</p>
        <div className="chips">
          {g.platforms.map((p) => <i key={p}>{PLATFORM[p]}</i>)}
          {g.genres.map((x) => <i key={x} className="g">{x}</i>)}
        </div>
        <p>{g.summary}</p>
        <ul className="facts">
          <li><b>{Math.round(g.positive_ratio * 100)}%</b> 긍정 리뷰</li>
          <li><b>{g.time_to_beat_hours}시간</b> 클리어(IGDB)</li>
          {g.concurrent_players > 0 && <li><b>{g.concurrent_players.toLocaleString('ko-KR')}</b> 명 접속 중</li>}
        </ul>
        {g.insights?.length > 0 && (
          <ul className="insights" aria-label="분석 태그">
            {g.insights.map((t) => (
              <li key={t.code}>
                <Link to={`/analysis/${t.analysis}`} className={`pill tone-${t.tone}`}>{t.label}</Link>
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
            <small>
              현재 {won(d.current_krw)} · 역대 최저 {won(d.lowest_krw)} ({dateKST(d.lowest_date)}) ·
              최저가 대비 {d.vs_lowest_pct > 0 ? '+' : ''}{d.vs_lowest_pct}%
            </small>
          </div>
        )}
      </State>
      <State s={p}>
        {(d) => (
          <div className="predict">
            <span>📅 다음 할인 예상 <b>{dateKST(d.next_sale_expected)}</b></span>
            <span>예상 할인율 <b>{d.expected_discount_pct}%</b></span>
            <span>평균 {d.avg_sale_interval_days}일 간격</span>
            <small className="muted">{d.basis} · 신뢰도 {{ low: '낮음', medium: '보통', high: '높음' }[d.confidence]}</small>
          </div>
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
          const pc = sorted.filter((i) => i.store !== 'danawa');
          const con = sorted.filter((i) => i.store === 'danawa');
          const Row = ({ i }) => {
            const best = i.price_krw === d.lowest.price_krw && i.store === d.lowest.store;
            return (
              <tr className={best ? 'best' : ''}>
                <td>{STORE_NAME[i.store]}{i.platform && ` · ${i.platform}`}</td>
                <td>{EDITION[i.edition]}</td>
                <td className="num">{i.discount_pct > 0 && <s>{won(i.regular_krw)}</s>} <b>{won(i.price_krw)}</b></td>
                <td>{i.discount_pct > 0 ? <em className="badge s">-{i.discount_pct}%</em> : ''}{best && <em className="badge low">최저가</em>}</td>
                <td><a href={i.url} onClick={() => api.event('store_click', { game_id: Number(id), store: i.store })}>구매 →</a></td>
              </tr>
            );
          };
          return (
            <>
              {pc.length > 0 && <><h3>PC 스토어</h3><table className="tbl"><tbody>{pc.map((i) => <Row key={i.store + i.edition} i={i} />)}</tbody></table></>}
              {con.length > 0 && <><h3>콘솔 (다나와)</h3><table className="tbl"><tbody>{con.map((i) => <Row key={i.platform + i.edition} i={i} />)}</tbody></table></>}
              <small className="muted">수집 {dateTimeKST(d.items[0].collected_at)} · 원화 환산 기준</small>
            </>
          );
        }}
      </State>
    </Section>
  );
}

function History({ id, user }) {
  const [days, setDays] = useState(180);
  const h = useAsync(() => api.history(id, days), [id, days]);
  const alerts = useAsync(() => (user ? api.alerts() : Promise.resolve({ items: [] })), [id, user]);
  const target = alerts.data?.items.find((a) => a.game_id === Number(id))?.target_price_krw;
  return (
    <Section
      title="가격 이력"
      right={
        <div className="seg">
          {[30, 90, 180, 365].map((d) => <button key={d} className={d === days ? 'on' : ''} onClick={() => setDays(d)}>{d}일</button>)}
        </div>
      }
    >
      <State s={h}>{(d) => <PriceChart items={d.items} target={target} />}</State>
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
      api.event('alert_add', { game_id: g.game_id });
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
      <small className="muted">리뷰 키워드로 본 참고 지표예요. 내 PC가 사양을 충족하는지는 반영하지 않아요. <Link to="/analysis/spec-trust">분석 보기</Link></small>
    </div>
  );
}

function Requirements({ id, user }) {
  const r = useAsync(() => api.requirements(id), [id]);
  const [check, setCheck] = useState(null);
  const run = async () => {
    try { setCheck({ data: await api.specCheck(id) }); } catch (e) { setCheck({ error: e }); }
  };
  const rows = [['os', 'OS'], ['cpu', 'CPU'], ['gpu', 'GPU'], ['ram_gb', 'RAM'], ['storage_gb', '저장공간']];
  return (
    <Section title="PC 사양">
      <State s={r}>
        {(d) => (
          <>
          <TrustBadge t={d.trust} />
          <table className="tbl spec">
            <thead><tr><th></th><th>최소</th><th>권장</th></tr></thead>
            <tbody>
              {rows.map(([k, label]) => (
                <tr key={k}>
                  <th>{label}</th>
                  <td>{k.endsWith('_gb') ? `${d.minimum[k]}GB` : d.minimum[k]}</td>
                  <td>{k.endsWith('_gb') ? `${d.recommended[k]}GB` : d.recommended[k]}</td>
                </tr>
              ))}
            </tbody>
          </table>
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
