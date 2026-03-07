import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./src/tests/e2e",
  use: {
    baseURL: "http://127.0.0.1:4173/static/web/",
    headless: true,
  },
  webServer: {
    command: "VITE_ROUTER_BASENAME=/static/web npm run dev -- --host 127.0.0.1 --port 4173",
    port: 4173,
    reuseExistingServer: false,
  },
});
