import { apiRequest } from "./client";

export interface DigestChannelSubscription {
  id: number;
  username: string;
  title: string | null;
  isActive: boolean;
  fetchErrorCount: number;
  lastError: string | null;
  createdAt: string;
  categoryId: number | null;
}

export interface DigestChannelsData {
  channels: DigestChannelSubscription[];
  activeCount: number;
  maxChannels: number | null;
  unlimitedChannels: boolean;
}

export interface DigestPreferences {
  deliveryTime: string;
  deliveryTimeSource: string;
  timezone: string;
  timezoneSource: string;
  hoursLookback: number;
  hoursLookbackSource: string;
  maxPostsPerDigest: number;
  maxPostsPerDigestSource: string;
  minRelevanceScore: number;
  minRelevanceScoreSource: string;
}

export interface DigestDelivery {
  id: number;
  deliveredAt: string;
  postCount: number;
  channelCount: number;
  digestType: string;
}

export interface DigestHistoryData {
  deliveries: DigestDelivery[];
  total: number;
  limit: number;
  offset: number;
}

export interface DigestTriggerResult {
  status: string;
  correlationId: string;
}

export interface ResolvedChannel {
  username: string;
  title: string | null;
  description: string | null;
  memberCount: number | null;
  photo: string | null;
}

export interface DigestChannelPost {
  id: number;
  date: string;
  text: string | null;
  contentType: string;
  views: number | null;
}

export interface DigestChannelPostsData {
  posts: DigestChannelPost[];
  total: number;
  limit: number;
  offset: number;
}

export interface DigestCategory {
  id: number;
  name: string;
}

interface SubscribeResponse {
  status: string;
  username: string;
}

interface TriggerChannelResult {
  status: string;
  channel: string;
  correlationId: string;
}

interface BulkUnsubscribeResponse {
  status: string;
  unsubscribed: string[];
}

interface BulkCategoryResponse {
  status: string;
  updated: number;
}

export function fetchDigestChannels(): Promise<DigestChannelsData> {
  return apiRequest<DigestChannelsData>("/v1/digest/channels");
}

export function subscribeDigestChannel(username: string): Promise<SubscribeResponse> {
  return apiRequest<SubscribeResponse>("/v1/digest/channels/subscribe", {
    method: "POST",
    body: JSON.stringify({ channel_username: username }),
  });
}

export function unsubscribeDigestChannel(username: string): Promise<SubscribeResponse> {
  return apiRequest<SubscribeResponse>("/v1/digest/channels/unsubscribe", {
    method: "POST",
    body: JSON.stringify({ channel_username: username }),
  });
}

export function resolveDigestChannel(username: string): Promise<ResolvedChannel> {
  return apiRequest<ResolvedChannel>("/v1/digest/channels/resolve", {
    method: "POST",
    body: JSON.stringify({ channel_username: username }),
  });
}

export function fetchDigestChannelPosts(
  username: string,
  limit = 10,
  offset = 0,
): Promise<DigestChannelPostsData> {
  return apiRequest<DigestChannelPostsData>(
    `/v1/digest/channels/${encodeURIComponent(username)}/posts?limit=${limit}&offset=${offset}`,
  );
}

export async function listDigestCategories(): Promise<DigestCategory[]> {
  const data = await apiRequest<{ categories: DigestCategory[] }>("/v1/digest/categories");
  return data.categories;
}

export function createDigestCategory(name: string): Promise<DigestCategory> {
  return apiRequest<DigestCategory>("/v1/digest/categories", {
    method: "POST",
    body: JSON.stringify({ name }),
  });
}

export function updateDigestCategory(id: number, name: string): Promise<DigestCategory> {
  return apiRequest<DigestCategory>(`/v1/digest/categories/${id}`, {
    method: "PATCH",
    body: JSON.stringify({ name }),
  });
}

export function deleteDigestCategory(id: number): Promise<void> {
  return apiRequest<void>(`/v1/digest/categories/${id}`, {
    method: "DELETE",
  });
}

export function assignDigestCategory(
  subscriptionId: number,
  categoryId: number | null,
): Promise<void> {
  return apiRequest<void>(`/v1/digest/channels/${subscriptionId}/category`, {
    method: "PATCH",
    body: JSON.stringify({ category_id: categoryId }),
  });
}

export function bulkUnsubscribeDigest(usernames: string[]): Promise<BulkUnsubscribeResponse> {
  return apiRequest<BulkUnsubscribeResponse>("/v1/digest/channels/bulk-unsubscribe", {
    method: "POST",
    body: JSON.stringify({ channel_usernames: usernames }),
  });
}

export function bulkAssignDigestCategory(
  subscriptionIds: number[],
  categoryId: number | null,
): Promise<BulkCategoryResponse> {
  return apiRequest<BulkCategoryResponse>("/v1/digest/channels/bulk-category", {
    method: "PATCH",
    body: JSON.stringify({ subscription_ids: subscriptionIds, category_id: categoryId }),
  });
}

export function fetchDigestPreferences(): Promise<DigestPreferences> {
  return apiRequest<DigestPreferences>("/v1/digest/preferences");
}

export function updateDigestPreferences(payload: Partial<{
  delivery_time: string;
  timezone: string;
  hours_lookback: number;
  max_posts_per_digest: number;
  min_relevance_score: number;
}>): Promise<DigestPreferences> {
  return apiRequest<DigestPreferences>("/v1/digest/preferences", {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function fetchDigestHistory(limit = 20, offset = 0): Promise<DigestHistoryData> {
  return apiRequest<DigestHistoryData>(`/v1/digest/history?limit=${limit}&offset=${offset}`);
}

export function triggerDigestNow(): Promise<DigestTriggerResult> {
  return apiRequest<DigestTriggerResult>("/v1/digest/trigger", {
    method: "POST",
  });
}

export function triggerSingleChannelDigest(channelUsername: string): Promise<TriggerChannelResult> {
  return apiRequest<TriggerChannelResult>("/v1/digest/trigger-channel", {
    method: "POST",
    body: JSON.stringify({ channel_username: channelUsername }),
  });
}
