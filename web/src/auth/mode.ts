import type { AuthMode } from "./types";

export function detectAuthMode(win: Window): AuthMode {
  const initData = win.Telegram?.WebApp?.initData;
  if (typeof initData === "string" && initData.trim().length > 0) {
    return "telegram-webapp";
  }
  return "jwt";
}
