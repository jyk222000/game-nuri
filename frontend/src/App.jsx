import { Routes, Route, Navigate } from 'react-router-dom';
import Header from './components/Header.jsx';
import Home from './pages/Home.jsx';
import Search from './pages/Search.jsx';
import GameDetail from './pages/GameDetail.jsx';
import Login from './pages/Login.jsx';
import MyPage from './pages/MyPage.jsx';
import { useAuth } from './auth.jsx';
import { API_MODE } from './api/client.js';

function Private({ children }) {
  const { user, ready } = useAuth();
  if (!ready) return <p className="muted pad">불러오는 중…</p>;
  return user ? children : <Navigate to="/login" replace />;
}

export default function App() {
  return (
    <>
      <Header />
      <main className="wrap">
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/search" element={<Search />} />
          <Route path="/games/:id" element={<GameDetail />} />
          <Route path="/login" element={<Login />} />
          <Route path="/me" element={<Private><MyPage /></Private>} />
          <Route path="*" element={<p className="muted pad">페이지를 찾을 수 없어요.</p>} />
        </Routes>
      </main>
      <footer className="foot">
        겜누리 · 데이터: ITAD, 다나와, IGDB, Steam
        {API_MODE === 'mock' && <> · 현재 <b>목(mock) 데이터</b>로 동작 중</>}
      </footer>
    </>
  );
}
