import { apiRequest } from "./client";
import type { SearchResult, TrendingTopic, PaginationInfo } from "../types/api";

interface SearchResponse {
  results: SearchResult[];
  pagination: PaginationInfo;
  query: string;
}

export function searchArticles(query: string, params?: {
  mode?: "hybrid" | "semantic" | "fts";
  limit?: number;
  offset?: number;
}): Promise<SearchResponse> {
  const q = new URLSearchParams({ q: query });
  if (params?.mode) q.set("mode", params.mode);
  q.set("limit", String(params?.limit ?? 20));
  q.set("offset", String(params?.offset ?? 0));
  return apiRequest(`/v1/search/search?${q}`);
}

export function getTrendingTopics(limit = 10, days = 7): Promise<{ topics: TrendingTopic[] }> {
  return apiRequest(`/v1/search/topics/trending?limit=${limit}&days=${days}`);
}
