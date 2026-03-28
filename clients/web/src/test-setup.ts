import "@testing-library/jest-dom/vitest";
import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";
import { setApiSession } from "./api/session";
import { setStoredTokens } from "./auth/storage";

afterEach(() => {
  cleanup();
  setApiSession({ mode: "jwt", accessToken: null, refreshToken: null, initData: "" });
  setStoredTokens(null);
  try { localStorage.clear(); } catch { /* jsdom may not support this */ }
});
