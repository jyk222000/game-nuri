import { Link } from 'react-router-dom';
import { won, platformName, hueOf } from '../lib/format.js';

// useAsync 결과를 로딩·오류·빈 상태로 나눠 그린다.
export function State({ s, children, isEmpty, emptyMsg = '결과가 없어요.' }) {
  if (s.loading && !s.data) return <p className="muted pad">불러오는 중…</p>;
  if (s.error) return <p className="err pad">{s.error.message}</p>;
  if (!s.data) return null;
  if (isEmpty && isEmpty(s.data)) return <p className="muted pad">{emptyMsg}</p>;
  return children(s.data);
}

// 표지: cover_url(IGDB)이 있으면 이미지, 없으면 game_id로 만든 색 그라데이션.
export const cover = (g) => {
  const hue = hueOf(g.game_id);
  const grad = `linear-gradient(135deg, hsl(${hue} 60% 38%), hsl(${(hue + 40) % 360} 55% 18%))`;
  return g.cover_url
    ? { background: grad, backgroundImage: `url("${g.cover_url}"), ${grad}`, backgroundSize: 'cover', backgroundPosition: 'center' }
    : { background: grad };
};

export function GameCard({ g, extra }) {
  return (
    <Link to={`/games/${g.game_id}`} className="card">
      <div className={`cover${g.cover_url ? ' has-img' : ''}`} style={cover(g)}>
        {!g.cover_url && <span className="cover-t">{g.name}</span>}
        {g.discount_pct > 0 && <em className="badge">-{g.discount_pct}%</em>}
      </div>
      <div className="card-b">
        <strong className="ellip">{g.name}</strong>
        <div className="chips">{g.platforms.map((p) => <i key={p}>{platformName(p)}</i>)}</div>
        <div className="price">
          {g.discount_pct > 0 && <s>{won(g.regular_krw)}</s>}
          <b>{won(g.price_krw)}</b>
        </div>
        {extra && <small className="muted">{extra}</small>}
      </div>
    </Link>
  );
}

export const Grid = ({ items, extra }) => (
  <div className="grid">{items.map((g) => <GameCard key={g.game_id} g={g} extra={extra?.(g)} />)}</div>
);

export const Section = ({ title, sub, right, children }) => (
  <section className="sec">
    <div className="sec-h"><h2>{title}{sub && <small>{sub}</small>}</h2>{right}</div>
    {children}
  </section>
);
