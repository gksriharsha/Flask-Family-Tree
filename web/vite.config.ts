import { defineConfig } from 'vite';

// Built into web/dist, which Flask serves at the application root. Same-origin means the
// browser never makes a cross-origin request, which removes the whole CORS problem class
// rather than configuring around it.
export default defineConfig({
  build: { outDir: 'dist', emptyOutDir: true },
  server: {
    port: 4200,
    // Only used by `npm run dev`; the production build is same-origin.
    proxy: { '/api': 'http://127.0.0.1:5000', '/health': 'http://127.0.0.1:5000' },
  },
});
