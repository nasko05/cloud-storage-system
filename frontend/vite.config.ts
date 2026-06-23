import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

// The build output mirrors the previous Create React App layout: it emits to
// `build/` with hashed assets under `build/static/`. That keeps the Dockerfile
// (which copies `frontend/build`) and the backend's `/static` mount unchanged.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
  },
  build: {
    outDir: 'build',
    assetsDir: 'static',
  },
});
