import { useState } from 'react';

// analysis/ 파이썬이 계산해 넘긴 차트 명세(JSON)를 그리기만 한다. 값을 다시 계산하지 않는다.
// 명세 형식은 analysis/gamenuri_analysis/charts.py 참고. 색 번호 1~8 = styles.css 의 --c1~--c8.
export const colorVar = (n) => `var(--c${(((n || 1) - 1) % 8) + 1})`;
const num = (v) => (v == null ? '-' : Number(v).toLocaleString('ko-KR', { maximumFractionDigits: 1 }));
const withUnit = (v, unit = '') => (v == null ? '-' : `${num(v)}${unit}`);
const scale = (a, b, c, d) => (v) => c + ((v - a) / (b - a || 1)) * (d - c);

function Legend({ items }) {
  if (!items.length) return null;
  return (
    <div className="legend">
      {items.map((i) => <span key={i.name}><i style={{ background: colorVar(i.color) }} />{i.name}</span>)}
    </div>
  );
}

function LineChart({ spec }) {
  const [hx, setHx] = useState(null);
  const W = 720, H = 280, P = { l: 52, r: 14, t: 16, b: 40 };
  const ser = spec.series.filter((s) => s.x.length);
  if (!ser.length) return <p className="muted">표시할 데이터가 없어요.</p>;
  const xs = ser.flatMap((s) => s.x);
  const ys = ser.flatMap((s) => s.y).filter((v) => v != null).concat((spec.hlines || []).map((h) => h.y));
  const x0 = Math.min(...xs), x1 = Math.max(...xs);
  let y0 = spec.zero ? 0 : spec.ymin ?? Math.min(...ys), y1 = Math.max(...ys);
  const pad = (y1 - y0) * 0.07 || 1;
  y1 += pad; if (!spec.zero && spec.ymin == null) y0 -= pad;
  const sx = scale(x0, x1, P.l, W - P.r), sy = scale(y0, y1, H - P.b, P.t);
  const xt = Array.from({ length: Math.min(6, xs.length) }, (_, i) => x0 + ((x1 - x0) * i) / Math.max(1, Math.min(6, xs.length) - 1));
  const xLabel = (v) => (spec.xlabels ? spec.xlabels[Math.round(v)] ?? '' : `${Math.round(v * 10) / 10}${spec.xunit || ''}`);
  const yt = [0, 1, 2, 3].map((i) => y0 + ((y1 - y0) * i) / 3);
  const kinds = Object.values(Object.fromEntries((spec.vlines || []).filter((v) => v.kind).map((v) => [v.kind, { name: v.kind, color: v.color }])));
  const legend = [...(ser.length > 1 ? ser.map((s) => ({ name: s.name, color: s.color })) : []), ...kinds];

  const onMove = (e) => {
    const r = e.currentTarget.getBoundingClientRect();
    const px = ((e.clientX - r.left) / r.width) * W;
    const v = x0 + ((px - P.l) / (W - P.l - P.r)) * (x1 - x0);
    const base = ser[0].x;
    setHx(base.reduce((b, x) => (Math.abs(x - v) < Math.abs(b - v) ? x : b), base[0]));
  };
  const near = hx == null ? [] : (spec.vlines || []).filter((v) => Math.abs(v.x - hx) <= (spec.xlabels ? 0.5 : 0));
  return (
    <div className="chart">
      <Legend items={legend} />
      <svg viewBox={`0 0 ${W} ${H}`} onMouseMove={onMove} onMouseLeave={() => setHx(null)} role="img" aria-label={spec.title}>
        {yt.map((t) => (
          <g key={t}><line x1={P.l} x2={W - P.r} y1={sy(t)} y2={sy(t)} className="grid-l" />
            <text x={P.l - 6} y={sy(t) + 4} textAnchor="end" className="ax">{num(Math.round(t * 10) / 10)}{spec.yunit || ''}</text></g>
        ))}
        {xt.map((t) => <text key={t} x={sx(t)} y={H - P.b + 16} textAnchor="middle" className="ax">{xLabel(t)}</text>)}
        {(spec.hlines || []).map((h) => (
          <g key={h.y}><line x1={P.l} x2={W - P.r} y1={sy(h.y)} y2={sy(h.y)} className="target" />
            <text x={W - P.r} y={sy(h.y) - 4} textAnchor="end" className="ax">{h.label}</text></g>
        ))}
        {(spec.vlines || []).map((v, i) => (
          <g key={`${v.x}-${i}`}>
            <line x1={sx(v.x)} x2={sx(v.x)} y1={P.t} y2={H - P.b} className="vl" style={{ stroke: v.color ? colorVar(v.color) : undefined }} />
            {!v.kind && <text x={sx(v.x) + 4} y={P.t + 10 + (i % 3) * 12} className="ax" style={{ fill: v.color ? colorVar(v.color) : undefined }}>{v.label}</text>}
          </g>
        ))}
        {ser.map((s) => (
          <polyline key={s.name} fill="none" strokeWidth="2.2" strokeLinejoin="round" stroke={colorVar(s.color)}
            points={s.x.map((x, i) => (s.y[i] == null ? null : `${sx(x)},${sy(s.y[i])}`)).filter(Boolean).join(' ')} />
        ))}
        {hx != null && <line x1={sx(hx)} x2={sx(hx)} y1={P.t} y2={H - P.b} className="cross" />}
        {hx != null && ser.map((s) => { const i = s.x.indexOf(hx); return i >= 0 && s.y[i] != null ? <circle key={s.name} cx={sx(hx)} cy={sy(s.y[i])} r="4" fill={colorVar(s.color)} /> : null; })}
        <text x={(P.l + W - P.r) / 2} y={H - 4} textAnchor="middle" className="ax">{spec.xlabel}</text>
      </svg>
      <div className="chart-info">
        {hx != null ? (
          <>
            <b>{xLabel(hx)}</b>
            {ser.map((s) => { const i = s.x.indexOf(hx); return i >= 0 ? <span key={s.name} className="hv"><i className="dotk" style={{ background: colorVar(s.color) }} />{ser.length > 1 ? `${s.name} ` : ''}{withUnit(s.y[i], spec.yunit)}</span> : null; })}
            {near.map((v) => <span key={v.label} className="hv ev">{v.label}</span>)}
          </>
        ) : <span className="muted">그래프 위에 마우스를 올려 보세요{spec.ylabel ? ` · ${spec.ylabel}` : ''}</span>}
      </div>
    </div>
  );
}

function Scatter({ spec }) {
  const [hov, setHov] = useState(null);
  const W = 720, H = 340, P = { l: 52, r: 16, t: 14, b: 44 };
  const pts = spec.points;
  const ext = (vals, pad) => [Math.min(...vals) - pad, Math.max(...vals) + pad];
  const [x0, x1] = spec.xlim || ext(pts.map((p) => p.x), 2);
  const [y0, y1] = spec.ylim || ext(pts.map((p) => p.y), 2);
  const sx = scale(x0, x1, P.l, W - P.r), sy = scale(y0, y1, H - P.b, P.t);
  const tick = (a, b) => Array.from({ length: 5 }, (_, i) => Math.round(a + ((b - a) * i) / 4));
  const color = Object.fromEntries(spec.groups.map((g) => [g.name, g.color]));
  const dg = [Math.max(x0, y0), Math.min(x1, y1)];
  return (
    <div className="chart">
      <Legend items={spec.groups} />
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={spec.title}>
        {tick(y0, y1).map((t) => <g key={`y${t}`}><line x1={P.l} x2={W - P.r} y1={sy(t)} y2={sy(t)} className="grid-l" /><text x={P.l - 6} y={sy(t) + 4} textAnchor="end" className="ax">{t}{spec.yunit || ''}</text></g>)}
        {(spec.xticks?.length ? spec.xticks : tick(x0, x1).map((t) => ({ x: t, label: `${t}${spec.xunit || ''}` }))).map((t) => (
          <text key={`x${t.x}`} x={sx(t.x)} y={H - P.b + 16} textAnchor="middle" className="ax">{t.label}</text>
        ))}
        {spec.diagonal && <line x1={sx(dg[0])} y1={sy(dg[0])} x2={sx(dg[1])} y2={sy(dg[1])} className="target" />}
        {spec.hline && <><line x1={P.l} x2={W - P.r} y1={sy(spec.hline.y)} y2={sy(spec.hline.y)} className="target" /><text x={W - P.r} y={sy(spec.hline.y) - 4} textAnchor="end" className="ax">{spec.hline.label}</text></>}
        {spec.curve.length > 0 && <polyline fill="none" className="curve" points={spec.curve.map(([a, b]) => `${sx(a)},${sy(b)}`).join(' ')} />}
        {pts.map((p, i) => (
          <circle key={i} cx={sx(p.x)} cy={sy(p.y)} r={p.label ? 6 : 4} fill={colorVar(color[p.group] || 1)} fillOpacity={p.label ? 0.95 : 0.6}
            stroke="var(--panel)" strokeWidth="1.5" onMouseEnter={() => setHov(p)} onMouseLeave={() => setHov(null)} />
        ))}
        {pts.filter((p) => p.label).map((p, i) => <text key={`l${i}`} x={Math.min(sx(p.x) + 9, W - 100)} y={sy(p.y) - 8} className="ax tip">{p.label}</text>)}
        <text x={(P.l + W - P.r) / 2} y={H - 4} textAnchor="middle" className="ax">{spec.xlabel}</text>
        <text x={12} y={(P.t + H - P.b) / 2} textAnchor="middle" className="ax" transform={`rotate(-90 12 ${(P.t + H - P.b) / 2})`}>{spec.ylabel}</text>
      </svg>
      <div className="chart-info">
        {hov ? <>{hov.label && <b>{hov.label} </b>}{spec.xlabel} {num(hov.x)}{spec.xunit || ''} · {spec.ylabel} {num(hov.y)}{spec.yunit || ''}{hov.group ? ` · ${hov.group}` : ''}</>
          : <span className="muted">점에 마우스를 올려 보세요{spec.curve_label ? ` · 점선: ${spec.curve_label}` : ''}</span>}
      </div>
    </div>
  );
}

function Bars({ spec }) {
  const vals = spec.items.map((i) => Math.abs(i.value ?? 0));
  const max = spec.vmax ?? Math.max(...vals, 1);
  if (spec.orient === 'v') {
    const n = spec.items.length, step = Math.ceil(n / 7);
    return (
      <div className="cols-wrap">
        <div className="cols">
          {spec.items.map((i) => (
            <div key={i.label} className="col" title={`${i.label}: ${withUnit(i.value, spec.unit)}`}>
              <div className="colbar" style={{ height: `${(Math.abs(i.value ?? 0) / max) * 100}%`, background: colorVar(i.color || spec.color) }} />
            </div>
          ))}
          {(spec.marks || []).map((mk) => <div key={mk.label} className="mark" style={{ left: `${(mk.pos / n) * 100}%` }}><span>{mk.label}</span></div>)}
        </div>
        <div className="col-labels">{spec.items.map((i, k) => <span key={i.label}>{k % step === 0 ? i.label : ''}</span>)}</div>
        {spec.xlabel && <small className="muted">{spec.xlabel}</small>}
      </div>
    );
  }
  return (
    <ul className="bars">
      {spec.items.map((i) => (
        <li key={i.label}>
          <span title={i.label}>{i.label}</span>
          <div>{i.value != null && <i style={{ width: `${Math.max(2, (Math.abs(i.value) / max) * 100)}%`, background: i.value < 0 ? 'var(--bad)' : colorVar(i.color || spec.color) }} />}</div>
          <em>{i.value == null ? <span className="err">{i.note}</span> : i.note ? <>{i.note}</> : withUnit(i.value, spec.unit)}</em>
        </li>
      ))}
    </ul>
  );
}

function Stacked({ spec }) {
  return (
    <div>
      <Legend items={spec.keys.map((k, i) => ({ name: k.label, color: i + 1 }))} />
      <ul className="stack">
        {spec.rows.map((r) => {
          const total = spec.keys.reduce((a, k) => a + (r.values[k.key] || 0), 0) || 1;
          return (
            <li key={r.label}>
              <span title={r.label}>{r.label}</span>
              <div>
                {spec.keys.map((k, i) => {
                  const v = r.values[k.key] || 0, p = (v / total) * 100;
                  return v ? <i key={k.key} style={{ width: `${p}%`, background: colorVar(i + 1) }} title={`${k.label} ${Math.round(p)}${spec.unit}`}>{p >= 9 ? Math.round(p) : ''}</i> : null;
                })}
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function Heatmap({ spec }) {
  const flat = spec.values.flat().filter((v) => v != null);
  const lo = Math.min(...flat), hi = Math.max(...flat);
  return (
    <div className="heat-wrap">
      <table className="heat">
        <thead><tr><th />{spec.cols.map((c) => <th key={c}>{c}</th>)}</tr></thead>
        <tbody>
          {spec.rows.map((r, ri) => (
            <tr key={r}>
              <th>{r}</th>
              {spec.values[ri].map((v, ci) => {
                const t = v == null ? 0 : (v - lo) / (hi - lo || 1);
                return <td key={ci} title={`${r} ${spec.cols[ci]} ${withUnit(v, spec.unit)}`}
                  style={{ background: `color-mix(in srgb, var(--brand) ${Math.round(t * 85 + 5)}%, transparent)`, color: t > 0.55 ? '#fff' : 'inherit' }}>{v == null ? '' : Math.round(v)}</td>;
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <small className="muted">값 = 평균 할인율(%) · 진할수록 깊은 할인</small>
    </div>
  );
}

const TYPES = { line: LineChart, scatter: Scatter, bars: Bars, stacked: Stacked, heatmap: Heatmap };

export function Chart({ spec }) {
  const C = TYPES[spec.type];
  return (
    <div className="panel">
      {spec.title && <h4 className="ctitle">{spec.title}</h4>}
      {C ? <C spec={spec} /> : <p className="err">지원하지 않는 차트: {spec.type}</p>}
    </div>
  );
}
