import { setStoredTokens } from "../auth/storage";
import type { AuthTokens } from "../auth/types";
import { normalizeKeys } from "../lib/case";
import { config } from "../lib/config";
import { getApiSession, setApiSession } from "./session";

const BASE_URL = config.apiBaseUrl;
const DEFAULT_TIMEOUT_MS = 20_000;

if (!config.apiBaseUrl && import.meta.env.DEV) {
  console.warn("[api] VITE_API_BASE_URL not set; using relative paths");
}

interface ApiErrorPayload {
  error?: {
    message?: string;
  };
}

interface ApiEnvelope<T> {
  success: boolean;
  data: T;
  meta?: unknown;
  error?: {
    code?: string;
    message?: string;
  };
}

function withTimeout(signal?: AbortSignal | null): AbortSignal {
  return signal ?? AbortSignal.timeout(DEFAULT_TIMEOUT_MS);
}

function getErrorMessage(status: number): string {
  if (status === 401) return "Authentication required.";
  if (status === 403) return "Access denied.";
  if (status === 404) return "Resource not found.";
  if (status === 429) return "Too many requests. Please try again.";
  return `Request failed (${status}).`;
}

async function parseJsonSafe<T>(response: Response): Promise<T | null> {
  try {
    return (await response.json()) as T;
  } catch {
    return null;
  }
}

async function refreshAccessToken(refreshToken: string): Promise<AuthTokens | null> {
  const response = await fetch(`${BASE_URL}/v1/auth/refresh`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ refresh_token: refreshToken }),
    signal: AbortSignal.timeout(DEFAULT_TIMEOUT_MS),
  });

  if (!response.ok) {
    return null;
  }

  const body = await parseJsonSafe<ApiEnvelope<{ tokens: AuthTokens; sessionId?: number | null }>>(response);
  if (!body?.data?.tokens?.accessToken) {
    return null;
  }

  const tokens = normalizeKeys(body.data.tokens);
  const normalized: AuthTokens = {
    accessToken: tokens.accessToken,
    refreshToken: tokens.refreshToken ?? refreshToken,
    expiresIn: tokens.expiresIn,
    tokenType: tokens.tokenType,
    sessionId: body.data.sessionId ?? null,
  };

  const current = getApiSession();
  setApiSession({
    ...current,
    accessToken: normalized.accessToken,
    refreshToken: normalized.refreshToken,
  });
  setStoredTokens(normalized);

  return normalized;
}

interface ApiRequestOptions extends RequestInit {
  _skipRefresh?: boolean;
}

async function requestOnce<T>(path: string, options: ApiRequestOptions = {}): Promise<T> {
  const session = getApiSession();
  const headers = new Headers(options.headers ?? {});

  if (!headers.has("Content-Type") && !(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }

  if (session.mode === "telegram-webapp" && session.initData) {
    headers.set("X-Telegram-Init-Data", session.initData);
  }

  if (session.mode === "jwt" && session.accessToken) {
    headers.set("Authorization", `Bearer ${session.accessToken}`);
  }

  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const { _skipRefresh: _skip, ...fetchOptions } = options;
  const response = await fetch(`${BASE_URL}${path}`, {
    ...fetchOptions,
    headers,
    signal: withTimeout(options.signal),
  });

  if (!response.ok) {
    const errorBody = await parseJsonSafe<ApiErrorPayload>(response);
    const message = errorBody?.error?.message ?? getErrorMessage(response.status);
    const error = new Error(message) as Error & { status?: number };
    error.status = response.status;
    throw error;
  }

  const json = await parseJsonSafe<ApiEnvelope<T>>(response);
  if (!json) {
    throw new Error("Invalid server response.");
  }

  if (!json.success) {
    const msg = json?.error?.message ?? "Request failed";
    throw Object.assign(new Error(msg), { status: response.status });
  }

  const payload = normalizeKeys(json.data ?? ({} as T));
  return payload;
}

export async function apiRequest<T>(path: string, options: ApiRequestOptions = {}): Promise<T> {
  try {
    return await requestOnce<T>(path, options);
  } catch (error) {
    const status = (error as { status?: number }).status;
    const session = getApiSession();

    if (
      status !== 401 ||
      session.mode !== "jwt" ||
      !session.refreshToken ||
      path === "/v1/auth/refresh" ||
      options._skipRefresh
    ) {
      throw error;
    }

    const refreshed = await refreshAccessToken(session.refreshToken);
    if (!refreshed) {
      setStoredTokens(null);
      setApiSession({ ...session, accessToken: null, refreshToken: null });
      throw new Error("Session expired. Please sign in again.");
    }

    return requestOnce<T>(path, { ...options, _skipRefresh: true });
  }
}
