import { getApiSession } from "./session";
import { config } from "../lib/config";
import { apiRequest } from "./client";

/** Flat subscription shape matching backend GET /v1/rss/feeds response. */
export interface RSSSubscription {
  subscriptionId: number;
  feedId: number;
  feedTitle: string | null;
  feedUrl: string;
  siteUrl: string | null;
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
  feeds: RSSSubscription[];
}

interface RSSFeedItemsData {
  feedId: number;
  items: RSSFeedItem[];
}

interface SubscribeResponse {
  subscriptionId: number;
  feedId: number;
  feedTitle: string | null;
  feedUrl: string;
}

interface UnsubscribeResponse {
  deleted: boolean;
  id: number;
}

interface RefreshResponse {
  feedId: number;
  newItems: number;
  notModified?: boolean;
}

interface ImportOPMLResponse {
  imported: number;
  errors: number;
  total: number;
}

export function fetchRSSSubscriptions(): Promise<RSSSubscriptionsData> {
  return apiRequest<RSSSubscriptionsData>("/v1/rss/feeds");
}

export function subscribeToFeed(url: string, categoryId?: number): Promise<SubscribeResponse> {
  return apiRequest<SubscribeResponse>("/v1/rss/feeds/subscribe", {
    method: "POST",
    body: JSON.stringify({ url, category_id: categoryId }),
  });
}

export function unsubscribeFromFeed(subscriptionId: number): Promise<UnsubscribeResponse> {
  return apiRequest<UnsubscribeResponse>(`/v1/rss/feeds/${subscriptionId}`, {
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

export async function exportOPML(): Promise<Blob> {
  const session = getApiSession();
  const headers: Record<string, string> = {};
  if (session.mode === "telegram-webapp" && session.initData) {
    headers["X-Telegram-Init-Data"] = session.initData;
  }
  if (session.mode === "jwt" && session.accessToken) {
    headers["Authorization"] = `Bearer ${session.accessToken}`;
  }
  const response = await fetch(`${config.apiBaseUrl}/v1/rss/export/opml`, { headers });
  if (!response.ok) throw new Error("OPML export failed");
  return response.blob();
}

export function importOPML(file: File): Promise<ImportOPMLResponse> {
  const formData = new FormData();
  formData.append("file", file);
  return apiRequest<ImportOPMLResponse>("/v1/rss/import/opml", {
    method: "POST",
    body: formData,
  });
}
