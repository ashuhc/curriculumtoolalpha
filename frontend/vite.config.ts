import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// The app calls the API with same-origin paths (/api/..., /ws). In development and
// `vite preview` these are proxied to the FastAPI backend, so no request can fall
// through to Vite's index.html fallback. BACKEND_URL overrides the default target.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ".", "");
  const backend = (env.BACKEND_URL || "http://localhost:8000").replace(/\/+$/, "");
  const proxy = {
    "/api": { target: backend, changeOrigin: true },
    "/ws": { target: backend.replace(/^http/, "ws"), ws: true, changeOrigin: true },
  };
  return {
    plugins: [react(), tailwindcss()],
    server: { port: 5173, strictPort: true, proxy },
    preview: { proxy },
  };
});
