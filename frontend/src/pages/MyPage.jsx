import { useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api/client.js';
import { useAuth } from '../auth.jsx';
import { useAsync } from '../lib/useAsync.js';
import { State, Grid } from '../components/ui.jsx';
import { won } from '../lib/format.js';

const TABS = [['wish', '찜 목록'], ['alerts', '목표가 알림'], ['reco', '맞춤 추천'], ['specs', '내 PC 사양'], ['profile', '내 정보']];

export default function MyPage() {
  const { user } = useAuth();
  const [tab, setTab] = useState('wish');
  return (
    <>
      <h1 className="h1">{user.name || user.email.split('@')[0]}님의 마이페이지 <small className="muted">{user.email}</small></h1>
      <div className="tabs" role="tablist">
        {TABS.map(([k, l]) => <button key={k} role="tab" aria-selected={tab === k} className={tab === k ? 'on' : ''} onClick={() => setTab(k)}>{l}</button>)}
      </div>
      {tab === 'wish' && <Wish />}
      {tab === 'alerts' && <Alerts />}
      {tab === 'reco' && <Reco />}
      {tab === 'specs' && <Specs />}
      {tab === 'profile' && <Profile />}
    </>
  );
}

function Wish() {
  const s = useAsync(() => api.wishlist(), []);
  return (
    <State s={s} isEmpty={(d) => !d.items.length} emptyMsg="아직 찜한 게임이 없어요. 게임 상세에서 ♡를 눌러 보세요.">
      {(d) => <Grid items={d.items} />}
    </State>
  );
}

function Alerts() {
  const a = useAsync(() => api.alerts(), []);
  return (
    <>
      <h3>설정한 목표가</h3>
      <p className="muted">목표가 이하가 되면 가입한 메일 주소로 알려드려요.</p>
      <State s={a} isEmpty={(d) => !d.items.length} emptyMsg="설정한 목표가가 없어요.">
        {(d) => (
          <table className="tbl">
            <thead><tr><th>게임</th><th>현재가</th><th>목표가</th><th>사용</th><th></th></tr></thead>
            <tbody>
              {d.items.map((x) => (
                <tr key={x.alert_id}>
                  <td><Link to={`/games/${x.game_id}`}>{x.game_name}</Link></td>
                  <td className="num">{won(x.current_krw)}</td>
                  <td className="num"><b>{won(x.target_price_krw)}</b></td>
                  <td><input type="checkbox" checked={x.active} onChange={async (e) => { await api.patchAlert(x.alert_id, { active: e.target.checked }); a.reload(); }} aria-label="알림 사용" /></td>
                  <td><button className="link" onClick={async () => { await api.delAlert(x.alert_id); a.reload(); }}>삭제</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </State>
    </>
  );
}

function Reco() {
  const { refresh } = useAuth();
  const [steam, setSteam] = useState('');
  const [err, setErr] = useState(null);
  const reco = useAsync(() => api.recommendations(), []);
  const taste = useAsync(() => api.taste(), []);
  const connect = async (e) => {
    e.preventDefault(); setErr(null);
    try { await api.setSteam(steam); await refresh(); reco.reload(); taste.reload(); } catch (x) { setErr(x.message); }
  };
  if (reco.error?.code === 'STEAM_REQUIRED') {
    return (
      <form className="form narrow" onSubmit={connect}>
        <h3>Steam 연동</h3>
        <p className="muted">보유 게임과 플레이타임을 바탕으로 취향을 분석해요. 프로필을 공개로 설정해 주세요.</p>
        <label>Steam ID (17자리)
          <input value={steam} onChange={(e) => setSteam(e.target.value)} placeholder="76561198000000000" inputMode="numeric" />
        </label>
        <button className="btn pri">연동하기</button>
        {err && <small className="err">{err}</small>}
      </form>
    );
  }
  return (
    <>
      <h3>내 취향</h3>
      <State s={taste}>
        {(t) => (
          <div className="taste">
            <p><b>{t.style}</b></p>
            <small className="muted">보유 {t.owned_games}개 · 총 {t.total_playtime_hours.toLocaleString('ko-KR')}시간 플레이</small>
            {t.top_genres.map((g) => (
              <div className="bar" key={g.genre}><span>{g.genre}</span><div><i style={{ width: `${g.pct}%` }} /></div><em>{g.pct}%</em></div>
            ))}
          </div>
        )}
      </State>
      <h3>이런 게임은 어때요?</h3>
      <State s={reco}>{(d) => <Grid items={d.items} extra={(g) => g.reason} />}</State>
    </>
  );
}

function Profile() {
  const { user, refresh } = useAuth();
  const [name, setName] = useState(user.name || '');
  const [msg, setMsg] = useState(null);
  const save = async (e) => {
    e.preventDefault(); setMsg(null);
    try { await api.updateMe(name.trim()); await refresh(); setMsg({ ok: true, t: '저장했어요.' }); } catch (x) { setMsg({ ok: false, t: x.message }); }
  };
  return (
    <form className="form narrow" onSubmit={save}>
      <label>메일 (알림이 이 주소로 가요)<input value={user.email} disabled /></label>
      <label>닉네임<input value={name} maxLength={64} onChange={(e) => { setName(e.target.value); setMsg(null); }} placeholder="겜누리 사용자" required /></label>
      <button className="btn pri">저장</button>
      {msg && <small className={msg.ok ? 'ok' : 'err'}>{msg.t}</small>}
    </form>
  );
}

function Specs() {
  const s = useAsync(() => api.specs(), []);
  return <State s={s}>{(d) => <SpecForm init={d} />}</State>;
}
function SpecForm({ init }) {
  const [f, setF] = useState({ os: init.os ?? '', cpu: init.cpu, gpu: init.gpu, ram_gb: init.ram_gb ?? '' });
  const [saved, setSaved] = useState(false);
  const on = (k) => (e) => { setF({ ...f, [k]: e.target.value }); setSaved(false); };
  return (
    <form className="form narrow" onSubmit={async (e) => { e.preventDefault(); await api.setSpecs({ ...f, ram_gb: f.ram_gb === '' ? null : Number(f.ram_gb) }); setSaved(true); }}>
      <p className="muted">선택 입력이에요. 입력하면 게임 상세에서 AI가 사양 적합도를 판정해 줘요.</p>
      <label>OS<input value={f.os} onChange={on('os')} placeholder="Windows 11" /></label>
      <label>CPU<input value={f.cpu} onChange={on('cpu')} placeholder="Intel Core i5-12400" /></label>
      <label>GPU<input value={f.gpu} onChange={on('gpu')} placeholder="NVIDIA RTX 3060" /></label>
      <label>RAM(GB)<input type="number" value={f.ram_gb} onChange={on('ram_gb')} placeholder="16" /></label>
      <button className="btn pri">저장</button>
      {saved && <small className="ok">저장했어요.</small>}
    </form>
  );
}
