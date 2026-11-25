/// <reference types="vitest/config" />
import { readFileSync } from "node:fs";

import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

// Ports come from the project-root .env so start_server.py and Vite agree.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, "..", "");
  const backend = `http://127.0.0.1:${env.BACKEND_PORT || "8030"}`;
  // Platform version from the repository-root VERSION file (shown under the login card).
  const version = readFileSync(new URL("../VERSION", import.meta.url), "utf8").trim();
  return {
    plugins: [react()],
    define: { __APP_VERSION__: JSON.stringify(version) },
    server: {
      port: Number(env.FRONTEND_PORT || 5190),
      strictPort: true,
      // Keep the browser's Host header so Django sees the public origin (CSRF, cookies).
      proxy: { "/api": { target: backend }, "/healthz": { target: backend } },
    },
    build: { outDir: "dist", sourcemap: false },
    test: { environment: "node" },
  };
});
