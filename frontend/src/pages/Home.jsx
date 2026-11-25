import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../auth.jsx';
import { api } from '../api/client.js';
import { useAsync } from '../lib/useAsync.js';
import { State, Grid, Section } from '../components/ui.jsx';

const CHANGE = { up: '▲', down: '▼', same: '–', new: 'NEW' };

// 클리어 시간 구간 (api.md: '보통' 클리어 시간 기준)
const LENGTHS = [
  { key: 'short', label: '짧게', range: '10시간 이하' },
  { key: 'medium', label: '보통', range: '10~40시간' },
  { key: 'long', label: '길게', range: '40시간 초과' },
];

// 시간별 추천: 내 성향(보유 게임의 클리어 시간 중앙값, GET /api/me/taste의 preferred_length)에 맞는 탭을 먼저 보여 준다.
// 로그인·Steam 연동이 없거나 데이터가 적으면 '짧게'부터 보이고, 탭을 눌러 바꿀 수 있다.
function LengthPicks() {
  const { user, ready } = useAuth();
  const taste = useAsync(() => (user ? api.taste().catch(() => null) : Promise.resolve(null)), [user]);
  const [picked, setPicked] = useState(null);
  const mine = taste.data?.preferred_length || null;
  const tab = picked || (!ready || taste.loading ? null : mine || 'short'); // 로그인 확인이 끝나야 시작 탭을 정한다(깜빡임 방지)
  const list = useAsync(() => (tab ? api.games({ length: tab, sort: 'popular', size: 6 }) : Promise.resolve(null)), [tab]);
  const cur = LENGTHS.find((x) => x.key === tab);
  return (
    <Section
      title="⏱ 시간별 추천 게임"
      sub={mine ? '내 플레이 성향에 맞춰 골랐어요' : '클리어까지 걸리는 시간 기준 (IGDB)'}
    >
      <div className="lp-bar">
      <div className="seg lp-tabs" role="tablist" aria-label="클리어까지 걸리는 시간">
        {LENGTHS.map((x) => (
          <button key={x.key} role="tab" aria-selected={tab === x.key} className={tab === x.key ? 'on' : ''} onClick={() => setPicked(x.key)}>
            {x.label}<small> {x.range}</small>{mine === x.key && <em className="lp-mine">내 성향</em>}
          </button>
        ))}
      </div>
      {tab && <Link to={`/search?length=${tab}&sort=popular`}>전체 보기</Link>}
      </div>
      <State s={tab ? list : { loading: true, data: null }} isEmpty={(d) => !d.items.length} emptyMsg={`${cur ? cur.label : ''} 끝낼 수 있는 게임이 아직 없어요.`}>
        {(d) => <Grid items={d.items.slice(0, 6)} oneRow extra={(g) => (g.time_to_beat_hours != null ? `클리어까지 약 ${g.time_to_beat_hours}시간` : null)} />}
      </State>
    </Section>
  );
}

export default function Home() {
  const deals = useAsync(() => api.deals(), []);
  const popular = useAsync(() => api.popular(), []);
  const trending = useAsync(() => api.trending(), []);
  const top = useAsync(() => api.playersTop(), []);
  const rated = useAsync(() => api.games({ sort: 'rating', size: 6 }), []);

  return (
    <>
      <section className="hero">
        <h1>어디서, 언제 사는 게<br />가장 쌀까?</h1>
        <p>PC 스토어 8곳과 콘솔 가격을 한 번에 비교하고, 지금 살지 기다릴지 알려드려요.</p>
      </section>

      <div className="home-two">
        <div>
          <Section title="🔥 지금 할인 중" right={<Link to="/search?sort=discount">전체 보기</Link>}>
            <State s={deals} isEmpty={(d) => !d.items.length} emptyMsg="지금 할인 중인 게임이 없어요.">
              {(d) => <Grid items={d.items.slice(0, 6)} oneRow />}
            </State>
          </Section>
        </div>
        <aside>
          <Section title="실시간 검색어" sub="최근 1시간">
            <State s={trending}>
              {(d) => (
                <ol className="rank">
                  {d.items.map((t) => (
                    <li key={t.rank}>
                      <b>{t.rank}</b>
                      <Link to={`/search?q=${encodeURIComponent(t.query)}`}>{t.query}</Link>
                      <i className={`chg ${t.change}`}>{CHANGE[t.change]}</i>
                    </li>
                  ))}
                </ol>
              )}
            </State>
          </Section>
        </aside>
      </div>

      <Section title="⭐ 인기 게임" right={<Link to="/search?sort=popular">전체 보기</Link>}>
        <State s={popular}>{(d) => <Grid items={d.items.slice(0, 6)} oneRow />}</State>
      </Section>

      <LengthPicks />

      <Section title="🏆 평점 높은 게임" sub="평론가 점수 (IGDB 집계)" right={<Link to="/search?sort=rating">전체 보기</Link>}>
        <State s={rated} isEmpty={(d) => !d.items.length} emptyMsg="아직 보여 줄 게임이 없어요.">
          {(d) => <Grid items={d.items.slice(0, 6)} oneRow extra={(g) => (g.critic_score != null ? `평론가 ${g.critic_score}점` : null)} />}
        </State>
      </Section>

      <Section title="👥 지금 접속자가 많은 게임" sub="Steam 동시 접속자">
        <State s={top}>
          {(d) => <Grid items={d.items.slice(0, 6)} oneRow extra={(g) => (g.concurrent_players != null ? `${g.concurrent_players.toLocaleString('ko-KR')}명 접속 중` : null)} />}
        </State>
      </Section>
    </>
  );
}
