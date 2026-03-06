import { apiRequest } from "./client";

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
  max_channels: number | null;
  unlimited_channels?: boolean;
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
  return apiRequest("/v1/digest/channels");
}

export function subscribeChannel(username: string): Promise<{ status: string; username: string }> {
  return apiRequest("/v1/digest/channels/subscribe", {
    method: "POST",
    body: JSON.stringify({ channel_username: username }),
  });
}

export function unsubscribeChannel(username: string): Promise<{ status: string; username: string }> {
  return apiRequest("/v1/digest/channels/unsubscribe", {
    method: "POST",
    body: JSON.stringify({ channel_username: username }),
  });
}

export function fetchPreferences(): Promise<DigestPreferences> {
  return apiRequest("/v1/digest/preferences");
}

export function updatePreferences(prefs: Partial<{
  delivery_time: string;
  timezone: string;
  hours_lookback: number;
  max_posts_per_digest: number;
  min_relevance_score: number;
}>): Promise<DigestPreferences> {
  return apiRequest("/v1/digest/preferences", {
    method: "PATCH",
    body: JSON.stringify(prefs),
  });
}

export function fetchHistory(limit = 20, offset = 0): Promise<HistoryData> {
  return apiRequest(`/v1/digest/history?limit=${limit}&offset=${offset}`);
}

export function triggerDigest(): Promise<TriggerResult> {
  return apiRequest("/v1/digest/trigger", { method: "POST" });
}

export function triggerChannelDigest(channelUsername: string): Promise<{
  status: string;
  channel: string;
  correlation_id: string;
}> {
  return apiRequest("/v1/digest/trigger-channel", {
    method: "POST",
    body: JSON.stringify({ channel_username: channelUsername }),
  });
}
