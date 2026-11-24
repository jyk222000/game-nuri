import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// 기본은 실서버 모드. 개발 서버 /api 는 VITE_BACKEND_URL(기본 localhost:8000)로 프록시한다. 목은 VITE_API_MODE=mock.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: { '/api': { target: process.env.VITE_BACKEND_URL || 'http://localhost:8000', changeOrigin: true } },
  },
});
