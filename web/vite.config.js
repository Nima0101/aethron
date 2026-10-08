import { defineConfig } from 'vite';
export default defineConfig({
  base: './',
  build: { target: 'es2020' },
  server: { host: '127.0.0.1', strictPort: true },
});
