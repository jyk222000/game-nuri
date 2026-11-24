import { useState } from 'react';
import { won } from '../lib/format.js';

const DAY = 86400000;
const toT = (date) => Date.parse(`${date}T00:00:00Z`);
const dateLabel = (t) => new Date(t).toISOString().slice(0, 10).replaceAll('-', '.');
const wonTick = (n) => `${Math.round(n).toLocaleString('ko-KR')}원`;

// 눈금이 1·2·5 × 10^k 로 떨어지게 잡는다 (예: 0 / 20,000 / 40,000 / 60,000 / 80,000원)
function niceTicks(lo, hi, count = 5) {
  const range = hi - lo > 0 ? hi - lo : 1000;
  const raw = range / (count - 1);
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = ([1, 2, 5, 10].find((m) => m * mag >= raw) ?? 10) * mag;
  const start = Math.floor(lo / step) * step;
  const end = Math.max(Math.ceil(hi / step) * step, start + step);
  const out = [];
  for (let v = start; v <= end + step / 2; v += step) out.push(v);
  return out;
}

// 의존성 없이 SVG로 그린 가격 이력 차트 (날짜마다 점 하나, 점끼리 직선으로 잇는 꺾은선. 가로축은 시간 비례)
export default function PriceChart({ items, target, domain }) {
  const [hoverT, setHoverT] = useState(null);
  const W = 720, H = 260, P = { l: 78, r: 14, t: 12, b: 34 };
  const times = items.map((i) => toT(i.date));
  const prices = items.map((i) => i.price_krw);
  const t0 = times[0], t1 = times[times.length - 1];
  const span = Math.max(t1 - t0, DAY);

  // 세로축 위쪽 끝은 실제 가격 기준이다. 정가(regular_krw)는 스토어마다 달라서(GOG 등 해외 정가 환산) 쓰지 않는다.
  // domain = [최저, 최고]: 탭을 오가도 세로축이 같도록 밖에서 정해 주는 범위 (없으면 이 선의 범위)
  const top = Math.max(...prices, target ?? 0, domain?.[1] ?? 0);
  const bottom = Math.min(...prices, target ?? Infinity, domain?.[0] ?? Infinity);
  const yTicks = niceTicks(bottom, top);
  const yMin = yTicks[0], yMax = yTicks[yTicks.length - 1];

  const x = (t) => P.l + ((t - t0) / span) * (W - P.l - P.r);
  const y = (v) => P.t + (1 - (v - yMin) / Math.max(yMax - yMin, 1)) * (H - P.t - P.b);

  const d = items.map((_, i) => `${i === 0 ? 'M' : 'L'}${x(times[i])},${y(prices[i])}`).join('');
  const showDots = items.length <= 60; // 점이 너무 많으면 선만 그린다

  // 날짜 눈금: 시간 간격이 같은 5곳 (이력이 하루뿐이면 한 곳)
  // 기간이 며칠뿐이면(콘솔) 같은 날짜가 반복되지 않게 하루에 하나만 둔다.
  const nTicks = Math.min(5, Math.round((t1 - t0) / DAY) + 1);
  const xTicks = t1 > t0 ? Array.from({ length: nTicks }, (_, k) => t0 + (span * k) / (nTicks - 1)) : [t0];

  const lowIdx = prices.indexOf(Math.min(...prices));
  const onMove = (e) => {
    const r = e.currentTarget.getBoundingClientRect();
    const px = ((e.clientX - r.left) / r.width) * W;
    const t = t0 + ((px - P.l) / (W - P.l - P.r)) * span;
    setHoverT(Math.max(t0, Math.min(t1, t)));
  };
  // 마우스에서 가장 가까운 날짜의 점
  let hi = -1;
  if (hoverT != null) {
    let best = Infinity;
    times.forEach((t, i) => { const gap = Math.abs(t - hoverT); if (gap < best) { best = gap; hi = i; } });
  }
  const h = hi >= 0 ? items[hi] : null;

  return (
    <div className="chart">
      <svg viewBox={`0 0 ${W} ${H}`} onMouseMove={onMove} onMouseLeave={() => setHoverT(null)} role="img" aria-label="가격 이력 차트">
        {yTicks.map((t) => (
          <g key={t}>
            <line x1={P.l} x2={W - P.r} y1={y(t)} y2={y(t)} className="grid-l" />
            <text x={P.l - 8} y={y(t) + 4} textAnchor="end" className="ax">{wonTick(t)}</text>
          </g>
        ))}
        {xTicks.map((t, k) => (
          <g key={t}>
            <line x1={x(t)} x2={x(t)} y1={H - P.b} y2={H - P.b + 5} className="grid-l" />
            <text
              x={x(t)}
              y={H - P.b + 18}
              textAnchor={xTicks.length === 1 ? 'start' : k === 0 ? 'start' : k === xTicks.length - 1 ? 'end' : 'middle'}
              className="ax"
            >{dateLabel(t)}</text>
          </g>
        ))}
        <path d={d} className="line" />
        {showDots && items.map((it, i) => <circle key={it.date} cx={x(times[i])} cy={y(prices[i])} r="2.5" className="dot" />)}
        {target != null && (
          <>
            <line x1={P.l} x2={W - P.r} y1={y(target)} y2={y(target)} className="target" />
            <text x={W - P.r} y={y(target) - 4} textAnchor="end" className="ax tg">목표가 {wonTick(target)}</text>
          </>
        )}
        <circle cx={x(times[lowIdx])} cy={y(prices[lowIdx])} r="5" className="low" />
        {h && (
          <>
            <line x1={x(times[hi])} x2={x(times[hi])} y1={P.t} y2={H - P.b} className="cross" />
            <circle cx={x(times[hi])} cy={y(h.price_krw)} r="4.5" className="dot" />
          </>
        )}
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
