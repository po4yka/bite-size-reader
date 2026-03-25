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
        manualChunks(id: string) {
          if (id.includes("node_modules/react-dom") || id.includes("node_modules/react/") || id.includes("node_modules/react-router") || id.includes("node_modules/@tanstack/react-query")) {
            return "vendor";
          }
          if (id.includes("node_modules/@carbon/")) {
            return "carbon";
          }
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
        statements: 15,
        branches: 10,
        functions: 15,
        lines: 15,
      },
    },
  },
});
