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
  },
});
