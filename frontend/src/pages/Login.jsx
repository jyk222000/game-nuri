import { useState } from 'react';
import { Navigate, useNavigate } from 'react-router-dom';
import { useAuth } from '../auth.jsx';
import { API_MODE } from '../api/client.js';

export default function Login() {
  const { user, login } = useAuth();
  const nav = useNavigate();
  const [busy, setBusy] = useState(false);
  if (user) return <Navigate to="/me" replace />;

  return (
    <div className="login">
      <h1>겜누리 시작하기</h1>
      <p className="muted">구글 계정으로 가입·로그인하고 찜, 목표가 알림, 맞춤 추천을 사용해 보세요.</p>
      <button className="google" disabled={busy} onClick={async () => { setBusy(true); await login(); nav('/me'); }}>
        <span>G</span> 구글로 계속하기
      </button>
      {API_MODE === 'mock' && (
        <small className="muted">
          지금은 목(mock) 모드라 실제 구글 로그인 없이 테스트 계정으로 로그인돼요.
          real 모드에서는 <code>/api/auth/google/login</code>으로 이동합니다.
        </small>
      )}
    </div>
  );
}
