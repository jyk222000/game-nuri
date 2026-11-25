import { useSearchParams } from 'react-router-dom';
import { api } from '../api/client.js';
import { useAsync } from '../lib/useAsync.js';
import { State, Grid } from '../components/ui.jsx';
import { PLATFORM } from '../lib/format.js';

// 정렬에 맞춘 큰 제목 (검색어가 없을 때)
const SORT_TITLE = { '': '가나다순 게임', price: '가격 낮은 게임', discount: '할인 중인 게임', popular: '인기 게임', rating: '평점 높은 게임' };
const LENGTH_LABEL = { short: '짧게 (10시간 이하)', medium: '보통 (10~40시간)', long: '길게 (40시간 초과)' };

// 평점순이면 평론가 점수, 클리어까지 걸리는 시간 조건이 있으면 그 시간을 카드 아래에 보여 준다.
const extraOf = (f) => (f.sort !== 'rating' && !f.length ? undefined : (g) => {
  const parts = [];
  if (f.sort === 'rating') parts.push(g.critic_score != null ? `평론가 ${g.critic_score}점` : '평론가 점수 없음');
  if (f.length && g.time_to_beat_hours != null) parts.push(`클리어까지 약 ${g.time_to_beat_hours}시간`);
  return parts.join(' · ') || null;
});

export default function Search() {
  const [sp, setSp] = useSearchParams();
  const f = { q: sp.get('q') || '', platform: sp.get('platform') || '', genre: sp.get('genre') || '', length: sp.get('length') || '', sort: sp.get('sort') || '', page: sp.get('page') || '1' };
  const key = JSON.stringify(f);
  const res = useAsync(() => api.games({ ...f, size: 24 }), [key]); // 24 = 한 줄 칸 수(6·4·3·2)의 공배수
  const genres = useAsync(() => api.genres(), []);

  const set = (k, v) => {
    const n = new URLSearchParams(sp);
    if (v) n.set(k, v); else n.delete(k);
    if (k !== 'page') n.delete('page'); // 조건이 바뀌면 첫 페이지로
    setSp(n);
  };

  return (
    <>
      <h1 className="h1">{f.q ? <>“{f.q}” 검색 결과</> : SORT_TITLE[f.sort] || SORT_TITLE['']}{f.length && <small>클리어까지 {LENGTH_LABEL[f.length]}</small>}</h1>
      <div className="filters">
        <select value={f.platform} onChange={(e) => set('platform', e.target.value)} aria-label="플랫폼">
          <option value="">모든 플랫폼</option>
          {Object.entries(PLATFORM).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        <select value={f.genre} onChange={(e) => set('genre', e.target.value)} aria-label="장르">
          <option value="">모든 장르</option>
          {genres.data?.items.map((g) => <option key={g}>{g}</option>)}
        </select>
        <select value={f.length} onChange={(e) => set('length', e.target.value)} aria-label="클리어까지 걸리는 시간">
          <option value="">클리어까지 걸리는 시간 전체</option>
          <option value="short">짧게 (10시간 이하)</option>
          <option value="medium">보통 (10~40시간)</option>
          <option value="long">길게 (40시간 초과)</option>
        </select>
        <select value={f.sort} onChange={(e) => set('sort', e.target.value)} aria-label="정렬">
          <option value="">이름순</option>
          <option value="popular">인기순</option>
          <option value="rating">평점순</option>
          <option value="price">낮은 가격순</option>
          <option value="discount">할인율순</option>
        </select>
        {res.data && <span className="muted">{res.data.total}개</span>}
      </div>
      <State s={res} isEmpty={(d) => !d.items.length} emptyMsg="검색 결과가 없어요. 다른 단어로 찾아 보세요.">
        {(d) => (
          <>
            <Grid items={d.items} extra={extraOf(f)} />
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
