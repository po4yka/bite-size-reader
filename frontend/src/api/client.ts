const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

const DEFAULT_TIMEOUT_MS = 15_000;

const USER_MESSAGES: Record<number, string> = {
  401: "Session expired. Please reopen the app.",
  403: "Access denied.",
  404: "Not found.",
  429: "Too many requests. Please wait.",
};

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

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    if (body?.error?.message) {
      console.warn(`API error ${res.status}:`, body.error.message);
    }
    throw new Error(USER_MESSAGES[res.status] ?? `Request failed (${res.status})`);
  }

  const json = await res.json();
  return json.data;
}
