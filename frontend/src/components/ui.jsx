import { Link } from 'react-router-dom';
import { won, PLATFORM } from '../lib/format.js';

// useAsync 결과를 로딩·오류·빈 상태로 나눠 그린다.
export function State({ s, children, isEmpty, emptyMsg = '결과가 없어요.' }) {
  if (s.loading && !s.data) return <p className="muted pad">불러오는 중…</p>;
  if (s.error) return <p className="err pad">{s.error.message}</p>;
  if (!s.data) return null;
  if (isEmpty && isEmpty(s.data)) return <p className="muted pad">{emptyMsg}</p>;
  return children(s.data);
}

export const cover = (hue) => ({
  background: `linear-gradient(135deg, hsl(${hue} 60% 38%), hsl(${(hue + 40) % 360} 55% 18%))`,
});

export function GameCard({ g, extra }) {
  return (
    <Link to={`/games/${g.game_id}`} className="card">
      <div className="cover" style={cover(g.hue)}>
        <span className="cover-t">{g.name}</span>
        {g.discount_pct > 0 && <em className="badge">-{g.discount_pct}%</em>}
      </div>
      <div className="card-b">
        <strong className="ellip">{g.name}</strong>
        <div className="chips">{g.platforms.map((p) => <i key={p}>{PLATFORM[p]}</i>)}</div>
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
