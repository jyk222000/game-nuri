import { useState } from 'react';
import { won } from '../lib/format.js';

// 의존성 없이 SVG로 그린 가격 이력 차트 (계단식: 가격이 바뀔 때만 꺾인다)
export default function PriceChart({ items, target }) {
  const [hover, setHover] = useState(null);
  const W = 720, H = 240, P = { l: 56, r: 12, t: 12, b: 24 };
  const prices = items.map((i) => i.price_krw);
  const max = Math.max(...items.map((i) => i.regular_krw ?? i.price_krw));
  const min = Math.min(...prices, target ?? Infinity) * 0.9;
  const x = (i) => P.l + (i / Math.max(items.length - 1, 1)) * (W - P.l - P.r);
  const y = (v) => P.t + (1 - (v - min) / Math.max(max - min, 1)) * (H - P.t - P.b);

  let d = `M${x(0)},${y(prices[0])}`;
  for (let i = 1; i < items.length; i++) d += `L${x(i)},${y(prices[i - 1])}L${x(i)},${y(prices[i])}`;

  const lowIdx = prices.indexOf(Math.min(...prices));
  const ticks = [0, 0.5, 1].map((t) => min + (max - min) * t);
  const onMove = (e) => {
    const r = e.currentTarget.getBoundingClientRect();
    const px = ((e.clientX - r.left) / r.width) * W;
    const i = Math.round(((px - P.l) / (W - P.l - P.r)) * (items.length - 1));
    setHover(Math.max(0, Math.min(items.length - 1, i)));
  };
  const h = hover != null ? items[hover] : null;

  return (
    <div className="chart">
      <svg viewBox={`0 0 ${W} ${H}`} onMouseMove={onMove} onMouseLeave={() => setHover(null)} role="img" aria-label="가격 이력 차트">
        {ticks.map((t) => (
          <g key={t}>
            <line x1={P.l} x2={W - P.r} y1={y(t)} y2={y(t)} className="grid-l" />
            <text x={P.l - 6} y={y(t) + 4} textAnchor="end" className="ax">{Math.round(t / 1000)}천</text>
          </g>
        ))}
        <path d={d} className="line" />
        {target != null && (
          <>
            <line x1={P.l} x2={W - P.r} y1={y(target)} y2={y(target)} className="target" />
            <text x={W - P.r} y={y(target) - 4} textAnchor="end" className="ax tg">목표가</text>
          </>
        )}
        <circle cx={x(lowIdx)} cy={y(prices[lowIdx])} r="5" className="low" />
        {h && (
          <>
            <line x1={x(hover)} x2={x(hover)} y1={P.t} y2={H - P.b} className="cross" />
            <circle cx={x(hover)} cy={y(h.price_krw)} r="4" className="dot" />
          </>
        )}
        <text x={P.l} y={H - 6} className="ax">{items[0].date}</text>
        <text x={W - P.r} y={H - 6} textAnchor="end" className="ax">{items[items.length - 1].date}</text>
      </svg>
      <div className="chart-info">
        {h ? (
          <><b>{h.date}</b> {won(h.price_krw)} {h.discount_pct > 0 && <span className="ok">-{h.discount_pct}%</span>}</>
        ) : (
          <span className="muted">● 기간 최저 {won(prices[lowIdx])} ({items[lowIdx].date}) — 그래프 위에 마우스를 올려 보세요</span>
        )}
      </div>
    </div>
  );
}
