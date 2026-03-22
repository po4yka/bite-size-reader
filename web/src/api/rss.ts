import { apiRequest } from "./client";

export interface RSSFeed {
  id: number;
  url: string;
  title: string | null;
  description: string | null;
  siteUrl: string | null;
  lastFetchedAt: string | null;
  fetchErrorCount: number;
  isActive: boolean;
}

export interface RSSSubscription {
  id: number;
  feedId: number;
  feed: RSSFeed;
  categoryId: number | null;
  categoryName: string | null;
  isActive: boolean;
  createdAt: string;
}

export interface RSSFeedItem {
  id: number;
  guid: string;
  title: string | null;
  url: string | null;
  content: string | null;
  author: string | null;
  publishedAt: string | null;
}

interface RSSSubscriptionsData {
  subscriptions: RSSSubscription[];
}

interface RSSFeedItemsData {
  items: RSSFeedItem[];
  total: number;
  limit: number;
  offset: number;
}

interface SubscribeResponse {
  status: string;
  subscriptionId: number;
}

interface UnsubscribeResponse {
  status: string;
}

interface RefreshResponse {
  status: string;
  feedId: number;
}

interface ImportOPMLResponse {
  status: string;
  imported: number;
  errors: number;
}

export function fetchRSSSubscriptions(): Promise<RSSSubscriptionsData> {
  return apiRequest<RSSSubscriptionsData>("/v1/rss/subscriptions");
}

export function subscribeToFeed(url: string, categoryId?: number): Promise<SubscribeResponse> {
  return apiRequest<SubscribeResponse>("/v1/rss/subscribe", {
    method: "POST",
    body: JSON.stringify({ url, category_id: categoryId }),
  });
}

export function unsubscribeFromFeed(subscriptionId: number): Promise<UnsubscribeResponse> {
  return apiRequest<UnsubscribeResponse>(`/v1/rss/subscriptions/${subscriptionId}`, {
    method: "DELETE",
  });
}

export function fetchFeedItems(
  feedId: number,
  limit = 20,
  offset = 0,
): Promise<RSSFeedItemsData> {
  return apiRequest<RSSFeedItemsData>(
    `/v1/rss/feeds/${feedId}/items?limit=${limit}&offset=${offset}`,
  );
}

export function refreshFeed(feedId: number): Promise<RefreshResponse> {
  return apiRequest<RefreshResponse>(`/v1/rss/feeds/${feedId}/refresh`, {
    method: "POST",
  });
}

export function exportOPML(): Promise<Blob> {
  return apiRequest<Blob>("/v1/rss/opml/export");
}

export function importOPML(file: File): Promise<ImportOPMLResponse> {
  const formData = new FormData();
  formData.append("file", file);
  return apiRequest<ImportOPMLResponse>("/v1/rss/opml/import", {
    method: "POST",
    body: formData,
  });
}
