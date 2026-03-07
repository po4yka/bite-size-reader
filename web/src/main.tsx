import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "@carbon/styles/css/styles.css";
import "./styles.css";
import App from "./App";
import { AuthProvider } from "./auth/AuthProvider";

function setRootCssVar(name: string, value?: number | string): void {
  if (value === undefined || value === null || value === "") {
    return;
  }
  document.documentElement.style.setProperty(name, String(value));
}

function setThemeColorMeta(value?: string): void {
  if (!value) return;
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) {
    meta.setAttribute("content", value);
  }
}

function syncTelegramWebAppVisuals(webApp: TelegramWebApp): void {
  const colorScheme = webApp.colorScheme === "dark" ? "dark" : "light";
  document.documentElement.style.colorScheme = colorScheme;
  document.documentElement.dataset.telegramColorScheme = colorScheme;

  const theme = webApp.themeParams ?? {};
  setRootCssVar("--tg-theme-bg-color", theme.bg_color);
  setRootCssVar("--tg-theme-secondary-bg-color", theme.secondary_bg_color);
  setRootCssVar("--tg-theme-text-color", theme.text_color);
  setRootCssVar("--tg-theme-hint-color", theme.hint_color);
  setRootCssVar("--tg-theme-link-color", theme.link_color);
  setThemeColorMeta(
    theme.bg_color ?? (colorScheme === "dark" ? "#161616" : "#ffffff"),
  );
}

function syncTelegramViewport(webApp: TelegramWebApp): void {
  if (typeof webApp.viewportHeight === "number") {
    setRootCssVar("--tg-viewport-height", `${webApp.viewportHeight}px`);
  }
  if (typeof webApp.viewportStableHeight === "number") {
    setRootCssVar("--tg-viewport-stable-height", `${webApp.viewportStableHeight}px`);
  }
}

function initializeTelegramWebApp(): void {
  const webApp = window.Telegram?.WebApp;
  if (!webApp) return;

  syncTelegramWebAppVisuals(webApp);
  syncTelegramViewport(webApp);
  webApp.ready?.();
  webApp.expand?.();

  const handleThemeChanged = () => syncTelegramWebAppVisuals(webApp);
  const handleViewportChanged = () => syncTelegramViewport(webApp);

  webApp.onEvent?.("themeChanged", handleThemeChanged);
  webApp.onEvent?.("viewportChanged", handleViewportChanged);
  webApp.onEvent?.("safeAreaChanged", handleViewportChanged);
  webApp.onEvent?.("contentSafeAreaChanged", handleViewportChanged);
}

initializeTelegramWebApp();

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 15_000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

const routerBasename = import.meta.env.VITE_ROUTER_BASENAME ?? "/web";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter basename={routerBasename}>
        <AuthProvider>
          <App />
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>,
);
