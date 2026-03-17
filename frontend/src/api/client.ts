const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

const DEFAULT_TIMEOUT_MS = 15_000;

const USER_MESSAGES: Record<number, string> = {
  401: "Session expired. Please reopen the app.",
  403: "Access denied.",
  404: "Not found.",
  429: "Too many requests. Please wait.",
};

interface ApiEnvelope<T> {
  success: boolean;
  data?: T;
  error?: {
    code?: string;
    message?: string;
  };
  meta?: unknown;
}

function getInitData(): string {
  return window.Telegram?.WebApp?.initData ?? "";
}

export async function apiRequest<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    ...options,
    signal: options.signal ?? AbortSignal.timeout(DEFAULT_TIMEOUT_MS),
    headers: {
      "Content-Type": "application/json",
      "X-Telegram-Init-Data": getInitData(),
      ...options.headers,
    },
  });

  const body = await res.json().catch(() => null) as ApiEnvelope<T> | null;

  if (!res.ok) {
    const message = body?.error?.message ?? USER_MESSAGES[res.status] ?? `Request failed (${res.status})`;
    if (body?.error?.message) {
      console.warn(`API error ${res.status}:`, body.error.message);
    }
    const err = new Error(message) as Error & { status?: number };
    err.status = res.status;
    throw err;
  }

  if (body !== null && body.success === false) {
    const message = body.error?.message ?? `Request failed`;
    const err = new Error(message) as Error & { status?: number };
    err.status = res.status;
    throw err;
  }

  return body?.data as T;
}
