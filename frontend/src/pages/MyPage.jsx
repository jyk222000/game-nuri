import { useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api/client.js';
import { useAuth } from '../auth.jsx';
import { useAsync } from '../lib/useAsync.js';
import { State, Grid } from '../components/ui.jsx';
import { won, CLEAR_LENGTHS } from '../lib/format.js';

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
    <State s={s} isEmpty={(d) => !d.items.length} emptyMsg="아직 찜한 게임이 없어요. 게임 상세에서 ♡찜하기를 눌러 보세요.">
      {(d) => <Grid items={d.items} />}
    </State>
  );
}

// 목표가를 그 자리에서 수정한다. Enter 저장, Esc 취소. 잘못된 값은 입력칸 아래에 이유를 보여 준다.
function TargetEdit({ x, onSave }) {
  const [editing, setEditing] = useState(false);
  const [val, setVal] = useState('');
  const [err, setErr] = useState(null);
  const [saving, setSaving] = useState(false);
  const start = () => { setVal(String(x.target_price_krw)); setErr(null); setEditing(true); };
  const cancel = () => { setEditing(false); setErr(null); };
  const save = async () => {
    const n = Number(val);
    if (!val || !Number.isFinite(n) || n <= 0) { setErr('0원보다 큰 금액을 입력해 주세요'); return; }
    if (Math.round(n) === x.target_price_krw) { cancel(); return; } // 바뀐 게 없으면 그냥 닫는다
    setSaving(true);
    try { await onSave(Math.round(n)); setEditing(false); setErr(null); } catch (e) { setErr(e.message || '저장하지 못했어요'); } finally { setSaving(false); }
  };
  if (!editing) {
    return (
      <span className="al-target">
        <b>{won(x.target_price_krw)}</b>
        <button className="al-edit" onClick={start} aria-label={`${x.game_name} 목표가 수정`}>수정</button>
      </span>
    );
  }
  return (
    <div className="al-edit-form">
      <div className="al-edit-row">
        <input
          type="number" min="1" step="10" autoFocus value={val} disabled={saving}
          onChange={(e) => setVal(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); save(); } else if (e.key === 'Escape') cancel(); }}
          aria-label={`${x.game_name} 목표가(원)`}
        />
        <button className="btn pri sm" onClick={save} disabled={saving}>{saving ? '저장 중…' : '저장'}</button>
        <button className="btn sm" onClick={cancel} disabled={saving}>취소</button>
      </div>
      {err && <small className="err">{err}</small>}
    </div>
  );
}

function Alerts() {
  const a = useAsync(() => api.alerts(), []);
  // 변경·삭제 뒤에 목록을 다시 불러온다. 실패하면 이유를 알려 준다.
  const act = async (fn) => {
    try { await fn(); a.reload(); } catch (e) { alert(e.message || '요청에 실패했어요'); }
  };
  return (
    <>
      <h3>설정한 목표가</h3>
      <p className="muted">목표가 이하가 되면 가입한 메일 주소로 알려드려요.</p>
      <State s={a} isEmpty={(d) => !d.items.length} emptyMsg="설정한 목표가가 없어요.">
        {(d) => (
          <div className="tbl-wrap">
            <table className="tbl al-tbl">
              <thead>
                <tr><th>게임</th><th className="num">현재가</th><th className="num">목표가</th><th>상태</th><th className="c">알림</th><th className="c" /></tr>
              </thead>
              <tbody>
                {d.items.map((x) => {
                  // 현재가가 목표가 이하면 도달, 아니면 남은 금액을 보여 준다
                  const left = x.current_krw != null ? x.current_krw - x.target_price_krw : null;
                  return (
                    <tr key={x.alert_id} className={x.active ? undefined : 'off'}>
                      <td><Link to={`/games/${x.game_id}`}>{x.game_name}</Link></td>
                      <td className="num">{x.current_krw != null ? won(x.current_krw) : '–'}</td>
                      <td className="num"><TargetEdit x={x} onSave={(n) => api.patchAlert(x.alert_id, { target_price_krw: n }).then(() => a.reload())} /></td>
                      <td>
                        {left == null ? <span className="al-state wait">–</span>
                          : left <= 0 ? <span className="al-state hit">목표가 도달</span>
                            : <span className="al-state wait">{won(left)} 남음</span>}
                      </td>
                      <td className="c">
                        <label className="switch" title={x.active ? '알림 끄기' : '알림 켜기'}>
                          <input type="checkbox" checked={x.active} onChange={(e) => act(() => api.patchAlert(x.alert_id, { active: e.target.checked }))} aria-label={`${x.game_name} 알림 사용`} />
                          <span />
                        </label>
                      </td>
                      <td className="c">
                        <button className="al-del" onClick={() => window.confirm(`“${x.game_name}” 목표가 알림을 삭제할까요?`) && act(() => api.delAlert(x.alert_id))}>삭제</button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </State>
    </>
  );
}

// 게임당 평균 플레이 시간 = 총 플레이 시간 ÷ 보유 게임 수 (소수 첫째 자리, .0은 뺀다). 보유 게임이 없으면 표시하지 않는다.
const avgPlay = (t) => (t.owned_games > 0 ? Number((t.total_playtime_hours / t.owned_games).toFixed(1)) : null);
// 클리어까지 걸리는 시간 성향 문구 (Steam 플레이 기록 + IGDB 클리어 시간으로 백엔드가 계산한 preferred_length). 없으면 표시하지 않는다.
const lengthPhrase = (t) => CLEAR_LENGTHS.find((x) => x.key === t.preferred_length)?.desc || null;

// 연동한 Steam ID를 보여 주고, 바꾸거나 보유 게임을 새로 가져온다. (PUT /api/me/steam)
// 계약: 같은 ID로 다시 부르면 보유 게임을 새로 고치고, Steam 조회가 실패하면 Steam ID도 저장하지 않는다(그대로 유지).
function SteamLink({ steamId, onChanged }) {
  const { refresh } = useAuth();
  const [editing, setEditing] = useState(false);
  const [val, setVal] = useState('');
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState(null);
  const save = async (id) => {
    if (!/^\d{17}$/.test(id)) { setMsg({ ok: false, t: 'Steam ID는 17자리 숫자예요.' }); return; }
    setBusy(true); setMsg(null);
    try {
      const r = await api.setSteam(id);
      await refresh();
      onChanged();
      setEditing(false);
      setMsg({ ok: true, t: `보유 게임 ${r.owned_games}개를 가져왔어요.` });
    } catch (e) { setMsg({ ok: false, t: e.message || '연동하지 못했어요' }); } finally { setBusy(false); }
  };
  return (
    <div className="steam-link">
      <div className="steam-row">
        <span className="muted">연동된 Steam ID</span>
        <code>{steamId}</code>
        {!editing && (
          <>
            <button className="btn sm" onClick={() => { setVal(''); setMsg(null); setEditing(true); }} disabled={busy}>변경</button>
            <button className="btn sm" onClick={() => save(steamId)} disabled={busy} title="같은 ID로 보유 게임과 플레이 시간을 다시 가져와요">{busy ? '가져오는 중…' : '보유 게임 새로고침'}</button>
          </>
        )}
      </div>
      {editing && (
        <form className="steam-row" onSubmit={(e) => { e.preventDefault(); save(val.trim()); }}>
          <input value={val} onChange={(e) => setVal(e.target.value)} placeholder="새 Steam ID (17자리)" inputMode="numeric" autoFocus disabled={busy} aria-label="새 Steam ID" />
          <button className="btn pri sm" disabled={busy}>{busy ? '확인하는 중…' : '저장'}</button>
          <button type="button" className="btn sm" onClick={() => { setEditing(false); setMsg(null); }} disabled={busy}>취소</button>
        </form>
      )}
      {msg && <small className={msg.ok ? 'ok' : 'err'}>{msg.t}</small>}
      {editing && <small className="muted">Steam 프로필과 게임 세부 정보가 <b>공개</b>여야 가져올 수 있어요. 실패하면 기존 연동은 그대로 유지돼요.</small>}
    </div>
  );
}

function Reco() {
  const { user, refresh } = useAuth();
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
      {user?.steam_id && <SteamLink steamId={user.steam_id} onChanged={() => { reco.reload(); taste.reload(); }} />}
      <h3>내 취향</h3>
      <State s={taste}>
        {(t) => (
          <div className="taste">
            <p><b>{t.style}</b></p>
            <small className="muted">
              Steam 보유 게임 {t.owned_games}개 · 총 {t.total_playtime_hours.toLocaleString('ko-KR')}시간 플레이
              {avgPlay(t) != null && <> · 게임당 평균 {avgPlay(t)}시간</>}
              {lengthPhrase(t) && <> · <b className="lt-phrase">{lengthPhrase(t)}</b></>}
            </small>
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
