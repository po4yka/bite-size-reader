const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

function getInitData(): string {
  return window.Telegram?.WebApp?.initData ?? "";
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(`${BASE_URL}/v1/digest${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      "X-Telegram-Init-Data": getInitData(),
      ...options.headers,
    },
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body?.error?.message ?? `Request failed: ${res.status}`);
  }

  const json = await res.json();
  return json.data;
}

// Types

export interface ChannelSubscription {
  id: number;
  username: string;
  title: string | null;
  is_active: boolean;
  fetch_error_count: number;
  last_error: string | null;
  created_at: string;
}

export interface ChannelsData {
  channels: ChannelSubscription[];
  active_count: number;
  max_channels: number;
}

export interface DigestPreferences {
  delivery_time: string;
  delivery_time_source: string;
  timezone: string;
  timezone_source: string;
  hours_lookback: number;
  hours_lookback_source: string;
  max_posts_per_digest: number;
  max_posts_per_digest_source: string;
  min_relevance_score: number;
  min_relevance_score_source: string;
}

export interface DigestDelivery {
  id: number;
  delivered_at: string;
  post_count: number;
  channel_count: number;
  digest_type: string;
}

export interface HistoryData {
  deliveries: DigestDelivery[];
  total: number;
  limit: number;
  offset: number;
}

export interface TriggerResult {
  status: string;
  correlation_id: string;
}

// API methods

export function fetchChannels(): Promise<ChannelsData> {
  return request("/channels");
}

export function subscribeChannel(username: string): Promise<{ status: string; username: string }> {
  return request("/channels/subscribe", {
    method: "POST",
    body: JSON.stringify({ channel_username: username }),
  });
}

export function unsubscribeChannel(username: string): Promise<{ status: string; username: string }> {
  return request("/channels/unsubscribe", {
    method: "POST",
    body: JSON.stringify({ channel_username: username }),
  });
}

export function fetchPreferences(): Promise<DigestPreferences> {
  return request("/preferences");
}

export function updatePreferences(prefs: Partial<{
  delivery_time: string;
  timezone: string;
  hours_lookback: number;
  max_posts_per_digest: number;
  min_relevance_score: number;
}>): Promise<DigestPreferences> {
  return request("/preferences", {
    method: "PATCH",
    body: JSON.stringify(prefs),
  });
}

export function fetchHistory(limit = 20, offset = 0): Promise<HistoryData> {
  return request(`/history?limit=${limit}&offset=${offset}`);
}

export function triggerDigest(): Promise<TriggerResult> {
  return request("/trigger", { method: "POST" });
}
