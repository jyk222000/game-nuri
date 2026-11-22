import { Link } from 'react-router-dom';
import { api } from '../api/client.js';
import { useAsync } from '../lib/useAsync.js';
import { State, Grid, Section } from '../components/ui.jsx';

const CHANGE = { up: '▲', down: '▼', same: '–', new: 'NEW' };

export default function Home() {
  const deals = useAsync(() => api.deals(), []);
  const popular = useAsync(() => api.popular(), []);
  const trending = useAsync(() => api.trending(), []);
  const top = useAsync(() => api.playersTop(), []);
  const short = useAsync(() => api.short(), []);
  const low = useAsync(() => api.playersLow(), []);

  return (
    <>
      <section className="hero">
        <h1>어디서, 언제 사는 게<br />가장 쌀까?</h1>
        <p>PC 스토어 8곳과 콘솔 가격을 한 번에 비교하고, 지금 살지 기다릴지 알려드려요.</p>
      </section>

      <div className="two">
        <div>
          <Section title="🔥 지금 할인 중" right={<Link to="/search?sort=discount">전체 보기</Link>}>
            <State s={deals} isEmpty={(d) => !d.items.length} emptyMsg="지금 할인 중인 게임이 없어요.">
              {(d) => <Grid items={d.items.slice(0, 6)} />}
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

      <Section title="⭐ 인기 게임">
        <State s={popular}>{(d) => <Grid items={d.items} />}</State>
      </Section>

      <Section title="👥 지금 접속자가 많은 게임" sub="Steam 동시 접속자">
        <State s={top}>
          {(d) => <Grid items={d.items} extra={(g) => `${g.concurrent_players.toLocaleString('ko-KR')}명 접속 중`} />}
        </State>
      </Section>

      <Section title="⏱ 짧게 끝낼 수 있는 게임" sub="IGDB 클리어 시간 기준">
        <State s={short}>{(d) => <Grid items={d.items.slice(0, 6)} extra={(g) => `클리어 약 ${g.time_to_beat_hours}시간`} />}</State>
      </Section>

      <Section title="⚠ 접속자가 적은 온라인 게임" sub="매칭이 어려울 수 있어요">
        <State s={low} isEmpty={(d) => !d.items.length}>
          {(d) => <Grid items={d.items} extra={(g) => g.warning} />}
        </State>
      </Section>
    </>
  );
}
