import { apiRequest } from "./client";

export interface DigestChannelSubscription {
  id: number;
  username: string;
  title: string | null;
  isActive: boolean;
  fetchErrorCount: number;
  lastError: string | null;
  createdAt: string;
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

interface SubscribeResponse {
  status: string;
  username: string;
}

interface TriggerChannelResult {
  status: string;
  channel: string;
  correlationId: string;
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
