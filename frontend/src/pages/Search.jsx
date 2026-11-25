import { useSearchParams } from 'react-router-dom';
import { api } from '../api/client.js';
import { useAsync } from '../lib/useAsync.js';
import { State, Grid } from '../components/ui.jsx';
import { PLATFORM } from '../lib/format.js';

export default function Search() {
  const [sp, setSp] = useSearchParams();
  const f = { q: sp.get('q') || '', platform: sp.get('platform') || '', genre: sp.get('genre') || '', tag: sp.get('tag') || '', sort: sp.get('sort') || '', page: sp.get('page') || '1' };
  const key = JSON.stringify(f);
  const res = useAsync(() => api.games(f), [key]);
  const genres = useAsync(() => api.genres(), []);
  const tags = useAsync(() => api.tags(), []);

  const set = (k, v) => {
    const n = new URLSearchParams(sp);
    if (v) n.set(k, v); else n.delete(k);
    if (k !== 'page') n.delete('page'); // 조건이 바뀌면 첫 페이지로
    setSp(n);
  };

  return (
    <>
      <h1 className="h1">{f.q ? <>“{f.q}” 검색 결과</> : f.sort === 'discount' ? '할인 중인 게임' : '전체 게임'}</h1>
      <div className="filters">
        <select value={f.platform} onChange={(e) => set('platform', e.target.value)} aria-label="플랫폼">
          <option value="">모든 플랫폼</option>
          {Object.entries(PLATFORM).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        <select value={f.genre} onChange={(e) => set('genre', e.target.value)} aria-label="장르">
          <option value="">모든 장르</option>
          {genres.data?.items.map((g) => <option key={g}>{g}</option>)}
        </select>
        <select value={f.tag} onChange={(e) => set('tag', e.target.value)} aria-label="태그">
          <option value="">모든 태그</option>
          {tags.data?.items.map((t) => <option key={t}>{t}</option>)}
        </select>
        <select value={f.sort} onChange={(e) => set('sort', e.target.value)} aria-label="정렬">
          <option value="">기본순</option>
          <option value="price">낮은 가격순</option>
          <option value="discount">할인율순</option>
        </select>
        {res.data && <span className="muted">{res.data.total}개</span>}
      </div>
      <State s={res} isEmpty={(d) => !d.items.length} emptyMsg="검색 결과가 없어요. 다른 단어로 찾아 보세요.">
        {(d) => (
          <>
            <Grid items={d.items} />
            {d.total > d.size && (
              <div className="pager pager-center">
                <button className="btn" disabled={d.page <= 1} onClick={() => set('page', d.page > 2 ? String(d.page - 1) : '')}>← 이전</button>
                <span className="muted">{d.page} / {Math.ceil(d.total / d.size)}</span>
                <button className="btn" disabled={d.page * d.size >= d.total} onClick={() => set('page', String(d.page + 1))}>다음 →</button>
              </div>
            )}
          </>
        )}
      </State>
    </>
  );
}
