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
  category_id?: number | null;
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

export interface ResolvedChannel {
  username: string;
  title: string;
  description: string | null;
  member_count: number | null;
}

export interface ChannelPost {
  id: number;
  date: string;
  text: string;
  topic_tag?: string | null;
}

export interface ChannelPostsData {
  posts: ChannelPost[];
  total: number;
}

export interface Category {
  id: number;
  name: string;
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

export function resolveChannel(username: string): Promise<ResolvedChannel> {
  return apiRequest("/v1/digest/channels/resolve", {
    method: "POST",
    body: JSON.stringify({ channel_username: username }),
  });
}

export function fetchChannelPosts(
  username: string,
  limit = 10,
  offset = 0,
): Promise<ChannelPostsData> {
  return apiRequest(
    `/v1/digest/channels/${encodeURIComponent(username)}/posts?limit=${limit}&offset=${offset}`,
  );
}

export function listCategories(): Promise<Category[]> {
  return apiRequest("/v1/digest/categories");
}

export function createCategory(name: string): Promise<Category> {
  return apiRequest("/v1/digest/categories", {
    method: "POST",
    body: JSON.stringify({ name }),
  });
}

export function updateCategory(id: number, name: string): Promise<Category> {
  return apiRequest(`/v1/digest/categories/${id}`, {
    method: "PATCH",
    body: JSON.stringify({ name }),
  });
}

export function deleteCategory(id: number): Promise<{ status: string }> {
  return apiRequest(`/v1/digest/categories/${id}`, {
    method: "DELETE",
  });
}

export function assignCategory(
  subscriptionId: number,
  categoryId: number | null,
): Promise<{ status: string }> {
  return apiRequest(`/v1/digest/channels/${subscriptionId}/category`, {
    method: "PATCH",
    body: JSON.stringify({ category_id: categoryId }),
  });
}

export function bulkUnsubscribe(
  usernames: string[],
): Promise<{ status: string; unsubscribed: string[] }> {
  return apiRequest("/v1/digest/channels/bulk-unsubscribe", {
    method: "POST",
    body: JSON.stringify({ channel_usernames: usernames }),
  });
}

export function bulkAssignCategory(
  subscriptionIds: number[],
  categoryId: number | null,
): Promise<{ status: string }> {
  return apiRequest("/v1/digest/channels/bulk-category", {
    method: "PATCH",
    body: JSON.stringify({ subscription_ids: subscriptionIds, category_id: categoryId }),
  });
}
