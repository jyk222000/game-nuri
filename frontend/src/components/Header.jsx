import { useEffect, useRef, useState } from 'react';
import { Link, NavLink, useNavigate } from 'react-router-dom';
import { api } from '../api/client.js';
import { useAuth } from '../auth.jsx';

export default function Header() {
  const nav = useNavigate();
  const { user, logout } = useAuth();
  const [q, setQ] = useState('');
  const [sugg, setSugg] = useState([]);
  const [open, setOpen] = useState(false);
  const box = useRef(null);

  useEffect(() => {
    if (!q.trim()) { setSugg([]); return; }
    const t = setTimeout(() => api.autocomplete(q).then((r) => setSugg(r.items)).catch(() => {}), 200);
    return () => clearTimeout(t);
  }, [q]);

  useEffect(() => {
    const close = (e) => box.current && !box.current.contains(e.target) && setOpen(false);
    document.addEventListener('mousedown', close);
    return () => document.removeEventListener('mousedown', close);
  }, []);

  const submit = (e) => {
    e.preventDefault();
    if (!q.trim()) return;
    api.event('search', { query: q.trim() });
    setOpen(false);
    nav(`/search?q=${encodeURIComponent(q.trim())}`);
  };

  return (
    <header className="hdr">
      <div className="wrap hdr-in">
        <Link to="/" className="logo">겜<span>누리</span></Link>
        <form className="searchbox" onSubmit={submit} ref={box}>
          <input
            value={q} placeholder="게임 검색 (예: 엘든, 발더스)"
            onChange={(e) => { setQ(e.target.value); setOpen(true); }} onFocus={() => setOpen(true)}
            aria-label="게임 검색"
          />
          <button>검색</button>
          {open && sugg.length > 0 && (
            <ul className="sugg">
              {sugg.map((s) => (
                <li key={s.game_id}>
                  <Link to={`/games/${s.game_id}`} onClick={() => { setOpen(false); setQ(''); }}>
                    {s.name} <small>{s.name_en}</small>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </form>
        <nav className="menu">
          <NavLink to="/search?sort=discount">할인</NavLink>
          <NavLink to="/analysis">분석</NavLink>
          {user ? (
            <>
              <NavLink to="/me">마이페이지</NavLink>
              <button className="link" onClick={async () => { await logout(); nav('/'); }}>로그아웃</button>
            </>
          ) : (
            <NavLink to="/login">로그인</NavLink>
          )}
        </nav>
      </div>
    </header>
  );
}
