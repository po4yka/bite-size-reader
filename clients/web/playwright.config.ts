import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./src/tests/e2e",
  use: {
    baseURL: "http://127.0.0.1:4173/static/web/",
    headless: true,
  },
  webServer: [
    {
      command:
        "VITE_ROUTER_BASENAME=/static/web npm run dev -- --host 127.0.0.1 --port 4173",
      port: 4173,
      reuseExistingServer: !process.env.CI,
    },
    {
      command: "npx http-server storybook-static -p 6006 --silent",
      url: "http://127.0.0.1:6006",
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
    },
  ],
  projects: [
    {
      name: "desktop",
      use: { viewport: { width: 1440, height: 900 } },
      testIgnore: /storybook-visual\.spec\.ts$/,
    },
    {
      name: "iPhone 12",
      use: { ...devices["iPhone 12"] },
      testIgnore: /storybook-visual\.spec\.ts$/,
    },
    {
      name: "Pixel 5",
      use: { ...devices["Pixel 5"] },
      testIgnore: /storybook-visual\.spec\.ts$/,
    },
    {
      name: "iPad Mini",
      use: { ...devices["iPad Mini"] },
      testIgnore: /storybook-visual\.spec\.ts$/,
    },
    {
      name: "storybook",
      testMatch: /storybook-visual\.spec\.ts$/,
      use: {
        baseURL: "http://127.0.0.1:6006",
        viewport: { width: 1024, height: 768 },
      },
    },
  ],
});
