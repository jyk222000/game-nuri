import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// 백엔드 준비 후: VITE_USE_MOCK=false 로 두고, 개발 서버 /api 를 백엔드로 프록시한다.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: { '/api': { target: process.env.VITE_BACKEND_URL || 'http://localhost:8000', changeOrigin: true } },
  },
});
