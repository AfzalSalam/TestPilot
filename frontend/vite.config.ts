import react from "@vitejs/plugin-react";
import path from "node:path";
import { defineConfig } from "vite";

// In development the Vite server proxies /api to the FastAPI backend, so the browser sees one
// origin (no CORS). In Docker, nginx does the same job (see nginx.conf).
export default defineConfig({
  plugins: [react()],
  resolve: { alias: { "@": path.resolve(__dirname, "src") } },
  server: {
    port: 5173,
    proxy: { "/api": { target: process.env.VITE_PROXY_TARGET ?? "http://localhost:8000", changeOrigin: true } },
  },
});
