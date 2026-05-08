import type { AuthTokens } from "./types";

const STORAGE_KEY = "ratatoskr_web_auth_tokens";

type Listener = (tokens: AuthTokens | null) => void;

const listeners = new Set<Listener>();

interface StorageOptions {
  /**
   * When true (default for legacy Telegram/secret-login callers), tokens go
   * to localStorage and survive browser close. When false, tokens go to
   * sessionStorage and vanish on close -- the credentials-login Remember
   * Me=false mode. The chosen bucket is encoded into the persisted envelope
   * so refresh handlers can write back to the same place.
   */
  persistent: boolean;
}

function getLocalStorage(): Storage | null {
  return safeStorage(window.localStorage);
}

function getSessionStorage(): Storage | null {
  return safeStorage(window.sessionStorage);
}

function safeStorage(storage: Storage | undefined): Storage | null {
  if (!storage) return null;
  if (typeof storage.getItem !== "function") return null;
  if (typeof storage.setItem !== "function") return null;
  if (typeof storage.removeItem !== "function") return null;
  return storage;
}

function readFrom(storage: Storage | null): AuthTokens | null {
  try {
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

/**
 * Read the active token envelope.
 *
 * sessionStorage wins over localStorage so a "non-remembered" credentials
 * login overrides any stale localStorage row from a previous session.
 */
export function getStoredTokens(): AuthTokens | null {
  const fromSession = readFrom(getSessionStorage());
  if (fromSession) return fromSession;
  return readFrom(getLocalStorage());
}

/**
 * Persist the token envelope to the bucket implied by ``opts.persistent``.
 *
 * Always clears the OTHER bucket so reads can't fall back to a stale row.
 * When ``opts`` is omitted, the persistent flag from the envelope itself
 * (set by the login API client) is used; a missing flag defaults to true
 * to preserve legacy Telegram/secret-login behavior.
 */
export function setStoredTokens(
  tokens: AuthTokens | null,
  opts?: StorageOptions,
): void {
  const local = getLocalStorage();
  const session = getSessionStorage();

  if (tokens) {
    const persistent = opts?.persistent ?? tokens.persistent ?? true;
    const envelope: AuthTokens = { ...tokens, persistent };
    const target = persistent ? local : session;
    const other = persistent ? session : local;
    if (target) {
      target.setItem(STORAGE_KEY, JSON.stringify(envelope));
    }
    if (other) {
      other.removeItem(STORAGE_KEY);
    }
    for (const listener of listeners) {
      listener(envelope);
    }
    return;
  }

  // Logout: drop both buckets.
  if (local) local.removeItem(STORAGE_KEY);
  if (session) session.removeItem(STORAGE_KEY);
  for (const listener of listeners) {
    listener(null);
  }
}

export function subscribeTokenChanges(listener: Listener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
