import type { AuthTokens } from "./types";

const STORAGE_KEY = "ratatoskr_web_auth_tokens";

type Listener = (tokens: AuthTokens | null) => void;

const listeners = new Set<Listener>();

function getStorage(): Storage | null {
  const storage = window.localStorage as Storage | undefined;
  if (!storage) return null;
  if (typeof storage.getItem !== "function") return null;
  if (typeof storage.setItem !== "function") return null;
  if (typeof storage.removeItem !== "function") return null;
  return storage;
}

export function getStoredTokens(): AuthTokens | null {
  try {
    const storage = getStorage();
    if (!storage) return null;
    const raw = storage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as AuthTokens;
    if (!parsed.accessToken) return null;
    return parsed;
  } catch {
    return null;
  }
}

export function setStoredTokens(tokens: AuthTokens | null): void {
  const storage = getStorage();
  if (storage) {
    if (tokens) {
      storage.setItem(STORAGE_KEY, JSON.stringify(tokens));
    } else {
      storage.removeItem(STORAGE_KEY);
    }
  }
  for (const listener of listeners) {
    listener(tokens);
  }
}

export function subscribeTokenChanges(listener: Listener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
