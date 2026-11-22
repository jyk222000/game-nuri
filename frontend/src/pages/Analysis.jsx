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
  // 파일이 없으면 Vite/nginx가 index.html(200)을 돌려주므로 JSON이 아닐 때도 '결과 없음'으로 본다.
  const isJson = (res.headers.get('content-type') || '').includes('json');
  if (!res.ok || !isJson) throw new Error('PENDING');
  return res.json();
}

// 그래프: 파이썬이 계산한 숫자를 웹이 직접 그림(마우스 올리면 값) / 이미지: 파이썬(matplotlib)이 만든 PNG
function Figure({ f, base }) {
  const hasCharts = f.charts?.length > 0;
  const hasImage = !!f.file; // PNG 없이 그래프만 있는 결과도 있다
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
      <figcaption>{f.caption}{mode === 'image' && hasImage && <> · <a href={src} download>PNG 저장</a></>}</figcaption>
    </figure>
  );
}

function Detail({ d }) {
  return (
    <Section title={d.title} sub={d.lead}>
      <ul className="take-list">{d.steps.map(([h, t]) => <li key={h} className="take"><b>{h}</b><br />{t}</li>)}</ul>
      <div className="tbl-wrap">
        <table className="tbl">
          <thead><tr><th>그대로 하면 생기는 문제</th><th>해결</th></tr></thead>
          <tbody>{d.problems.map(([p, a]) => <tr key={p}><td>{p}</td><td>{a}</td></tr>)}</tbody>
        </table>
      </div>
    </Section>
  );
}

// 게임을 골라 그 게임의 결과만 보는 영역 (summary.json 의 picker). 장르·등급 구분 없이 게임 단위로 본다.
function Picker({ p, base }) {
  const [id, setId] = useState(p.items[0].id);
  const it = p.items.find((x) => x.id === id) || p.items[0];
  const random = () => setId(p.items[Math.floor(Math.random() * p.items.length)].id);
  return (
    <Section title={p.title} sub={p.hint}>
      <div className="picker">
        <select value={it.id} onChange={(e) => setId(e.target.value)} aria-label="게임 선택">
          {p.items.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}
        </select>
        <button className="btn" onClick={random}>🎲 아무 게임</button>
        <small className="muted">{it.sub}</small>
      </div>
      <ul className="take-list">{it.summary.map((t) => <li key={t} className="take">{t}</li>)}</ul>
      {it.charts.map((c, i) => <Figure key={`${it.id}${i}`} f={{ title: c.title, charts: [c], file: it.files?.[i], caption: '' }} base={base} />)}
      {it.table && (
        <div className="tbl-wrap">
          <table className="tbl">
            <thead><tr>{it.table.columns.map((c) => <th key={c}>{c}</th>)}</tr></thead>
            <tbody>{it.table.rows.map((r, i) => <tr key={i}>{r.map((v, j) => <td key={j}>{v ?? '-'}</td>)}</tr>)}</tbody>
          </table>
        </div>
      )}
    </Section>
  );
}

export function AnalysisIndex() {
  return (
    <>
      <section className="hero small">
        <h1>데이터로 보는 게임 시장</h1>
        <p>할인·검색·리뷰·가격 데이터 8가지를 분석해 “언제, 어디서, 무엇을 살지”의 근거를 만들어요. (대상 게임 1,000개)</p>
      </section>
      <div className="agrid">
        {ANALYSES.map((a) => (
          <Link key={a.key} to={`/analysis/${a.key}`} className="acard">
            <span className="ico">{a.icon}</span>
            <small className="muted">A{a.no}</small>
            <strong>{a.title}</strong>
            <span className="muted">{a.question}</span>
            <small className="muted">난이도 {a.level} · 담당 {a.owner}</small>
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
      <p className="crumb"><Link to="/analysis">분석</Link> › A{meta.no}. {meta.title}</p>
      <h1 className="h1">A{meta.no}. {meta.icon} {meta.title}: <span className="muted">{meta.question}</span></h1>
      <div className="brief">
        <div>
          <b>분석 방법</b>
          <p>{meta.method}</p>
          <b>차트</b>
          <ul>{meta.charts.map((c) => <li key={c}>{c}</li>)}</ul>
        </div>
        <div>
          <b>인사이트 예</b>
          <p>{meta.insight}</p>
          <small className="muted">데이터: {meta.data}</small>
          <small className="muted">선행 조건: {meta.prereq} · 난이도 {meta.level} · 담당 {meta.owner}</small>
          {meta.caution?.map((c) => <small key={c} className="warn-t">⚠ {c}</small>)}
        </div>
      </div>
      {meta.detail && <Detail d={meta.detail} />}

      {s.error?.message === 'PENDING' ? (
        <p className="mockbar">분석 결과 대기 중이에요. 11/26 오전 분석용 CSV 전달 후 11/26~27에 채워져요. (선행 조건: {meta.prereq})</p>
      ) : (
      <State s={s}>
        {(d) => (
          <>
            {d.data_source === 'mock' && (
              <p className="mockbar">⚠ 목(mock) 데이터로 계산한 결과예요. 가설을 심어 둔 가짜 값이라 결론으로 쓰면 안 돼요. · {dateTimeKST(d.generated_at)} 생성</p>
            )}
            <Section title="핵심 요약">
              <ul className="take-list">{d.takeaways.map((t) => <li key={t} className="take">{t}</li>)}</ul>
            </Section>
            {d.picker && <Picker p={d.picker} base={`${BASE}/${key}`} />}
            <Section title="그래프">
              <div className="figs">
                {d.figures.map((f) => <Figure key={f.title} f={f} base={`${BASE}/${key}`} />)}
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
      )}

      <nav className="pager">
        {prev ? <Link to={`/analysis/${prev.key}`}>← {prev.title}</Link> : <span />}
        {next ? <Link to={`/analysis/${next.key}`}>{next.title} →</Link> : <span />}
      </nav>
    </>
  );
}
