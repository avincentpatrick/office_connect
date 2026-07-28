/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// Dev connectivity contract (api-standards §6): the browser is same-origin on
// :5174; /api is proxied to the FastAPI app so the oc_session cookie
// (Path=/api, SameSite=Lax) and the X-Requested-With CSRF header work without
// CORS. In the compose `web` service the target is http://app:8001; running
// Vite on the host falls back to localhost:8001.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5174,
    strictPort: true, // 5174 is the recorded port (Laragon owns 5173) — never drift
    host: true,
    watch: { usePolling: process.env.CHOKIDAR_USEPOLLING === "true" },
    proxy: {
      "/api": {
        target: process.env.VITE_API_PROXY_TARGET || "http://localhost:8001",
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    css: false,
  },
});
