import { Link, useParams } from 'react-router-dom';
import { useState } from 'react';
import { useAsync } from '../lib/useAsync.js';
import { Chart } from '../components/Charts.jsx';
import { State, Section } from '../components/ui.jsx';
import { ANALYSES, byKey } from './analysis/meta.js';
import { dateTimeKST } from '../lib/format.js';

// 분석 결과는 analysis/ 파이썬이 만든 정적 파일(PNG + summary.json)이다. (A)
// `python -m gamenuri_analysis.run_all --publish` 가 public/analysis-data/ 로 복사한다.
const BASE = '/analysis-data';

async function loadSummary(key) {
  const res = await fetch(`${BASE}/${key}/summary.json`);
  if (!res.ok) throw new Error('분석 결과가 아직 없어요. analysis/ 에서 run_all --publish 를 실행해 주세요.');
  return res.json();
}

// 그래프: 파이썬이 계산한 숫자를 웹이 직접 그림(마우스 올리면 값) / 이미지: 파이썬(matplotlib)이 만든 PNG
function Figure({ f, base }) {
  const hasCharts = f.charts?.length > 0;
  const [mode, setMode] = useState(hasCharts ? 'chart' : 'image');
  const src = `${base}/${f.file}`;
  return (
    <figure>
      <div className="fig-h">
        <b>{f.title}</b>
        {hasCharts && (
          <div className="seg" role="group" aria-label="보기 방식">
            <button className={mode === 'chart' ? 'on' : ''} onClick={() => setMode('chart')}>그래프</button>
            <button className={mode === 'image' ? 'on' : ''} onClick={() => setMode('image')}>이미지(파이썬)</button>
          </div>
        )}
      </div>
      {mode === 'chart'
        ? <div className={`panels n${f.charts.length}`}>{f.charts.map((c, i) => <Chart key={i} spec={c} />)}</div>
        : <img src={src} alt={f.title} loading="lazy" />}
      <figcaption>{f.caption}{mode === 'image' && <> · <a href={src} download>PNG 저장</a></>}</figcaption>
    </figure>
  );
}

export function AnalysisIndex() {
  return (
    <>
      <section className="hero small">
        <h1>데이터로 보는 게임 시장</h1>
        <p>할인·리뷰·플레이 데이터를 분석해 “언제, 무엇을 살지”의 근거를 만들어요.</p>
      </section>
      <div className="agrid">
        {ANALYSES.map((a) => (
          <Link key={a.key} to={`/analysis/${a.key}`} className="acard">
            <span className="ico">{a.icon}</span>
            <small className="muted">분석 {a.no}</small>
            <strong>{a.title}</strong>
            <span className="muted">{a.question}</span>
          </Link>
        ))}
      </div>
    </>
  );
}

export function AnalysisPage() {
  const { key } = useParams();
  const meta = byKey(key);
  const s = useAsync(() => (meta ? loadSummary(key) : Promise.reject(new Error('없는 분석이에요.'))), [key]);
  if (!meta) return <p className="muted pad">없는 분석이에요. <Link to="/analysis">목록으로</Link></p>;
  const prev = ANALYSES[meta.no - 2], next = ANALYSES[meta.no];

  return (
    <>
      <p className="crumb"><Link to="/analysis">분석</Link> › {meta.no}. {meta.title}</p>
      <h1 className="h1">{meta.icon} {meta.title}: <span className="muted">{meta.question}</span></h1>
      <div className="brief">
        <div>
          <b>찾을 현상</b>
          <ul>{meta.find.map((f) => <li key={f}>{f}</li>)}</ul>
        </div>
        <div>
          <b>인사이트</b>
          <p>{meta.insight}</p>
          <small className="muted">데이터: {meta.data}</small>
          {meta.caution && <small className="warn-t">⚠ {meta.caution}</small>}
          {meta.strength && <small className="ok">✔ {meta.strength}</small>}
        </div>
      </div>

      <State s={s}>
        {(d) => (
          <>
            {d.data_source === 'mock' && (
              <p className="mockbar">⚠ 목(mock) 데이터로 계산한 결과예요. 가설을 심어 둔 가짜 값이라 결론으로 쓰면 안 돼요. · {dateTimeKST(d.generated_at)} 생성</p>
            )}
            <Section title="핵심 요약">
              <ul className="take-list">{d.takeaways.map((t) => <li key={t} className="take">{t}</li>)}</ul>
            </Section>
            <Section title="그래프">
              <div className="figs">
                {d.figures.map((f) => <Figure key={f.file} f={f} base={`${BASE}/${key}`} />)}
              </div>
            </Section>
            {d.tables.map((t) => (
              <Section key={t.title} title={t.title} sub={t.note}>
                <div className="tbl-wrap">
                  <table className="tbl">
                    <thead><tr>{t.columns.map((c) => <th key={c}>{c}</th>)}</tr></thead>
                    <tbody>{t.rows.map((r, i) => <tr key={i}>{r.map((v, j) => <td key={j}>{v ?? '-'}</td>)}</tr>)}</tbody>
                  </table>
                </div>
              </Section>
            ))}
          </>
        )}
      </State>

      <nav className="pager">
        {prev ? <Link to={`/analysis/${prev.key}`}>← {prev.title}</Link> : <span />}
        {next ? <Link to={`/analysis/${next.key}`}>{next.title} →</Link> : <span />}
      </nav>
    </>
  );
}
