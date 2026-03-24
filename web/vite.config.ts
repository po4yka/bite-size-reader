import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  base: "/static/web/",
  build: {
    outDir: "../app/static/web",
    emptyOutDir: true,
    rollupOptions: {
      output: {
        manualChunks: {
          vendor: ["react", "react-dom", "react-router-dom", "@tanstack/react-query"],
          carbon: ["@carbon/react", "@carbon/icons-react"],
        },
      },
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: "./src/test-setup.ts",
    include: ["src/**/*.test.ts", "src/**/*.test.tsx"],
    coverage: {
      provider: "v8",
      reporter: ["text", "lcov"],
      include: ["src/**/*.{ts,tsx}"],
      exclude: [
        "src/**/*.test.{ts,tsx}",
        "src/testing/**",
        "src/api/generated.ts",
        "src/vite-env.d.ts",
        "src/telegram.d.ts",
      ],
      thresholds: {
        statements: 5,
        branches: 3,
        functions: 5,
        lines: 5,
      },
    },
  },
});
