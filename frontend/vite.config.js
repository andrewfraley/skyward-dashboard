import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// `npm run dev` serves the UI on :5173 and proxies /api to a locally running
// uvicorn on :8087 (8080 is taken by other local apps; the container still
// listens on 8080), so the frontend can be worked on without rebuilding the image.
export default defineConfig({
  plugins: [react()],
  base: './',
  server: {
    host: true,
    port: 5173,
    proxy: {
      '/api': process.env.SKYWARD_API || 'http://localhost:8087',
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
})
