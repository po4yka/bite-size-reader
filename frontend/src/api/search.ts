import { apiRequest } from "./client";
import type { SearchResult, TrendingTopic, PaginationInfo } from "../types/api";

interface SearchResponse {
  results: SearchResult[];
  pagination: PaginationInfo;
  query: string;
}

interface BackendPaginationInfo {
  total: number;
  limit: number;
  offset: number;
  hasMore: boolean;
}

interface BackendSearchResult {
  requestId: number;
  summaryId: number;
  url: string | null;
  title: string;
  domain: string | null;
  tldr: string | null;
  topicTags: string[] | null;
  relevanceScore: number | null;
  matchSignals?: string[] | null;
  createdAt: string;
}

interface BackendSearchPayload {
  results: BackendSearchResult[];
  pagination: BackendPaginationInfo;
  query: string;
}

interface BackendTrendingTopic {
  tag: string;
  count: number;
}

interface BackendTrendingPayload {
  tags: BackendTrendingTopic[];
}

function normalizeMode(mode: "hybrid" | "semantic" | "fts"): "hybrid" | "semantic" | "keyword" {
  if (mode === "fts") return "keyword";
  return mode;
}

function mapSearchResponse(payload: BackendSearchPayload): SearchResponse {
  return {
    results: payload.results.map((item) => ({
      id: item.summaryId,
      request_id: String(item.requestId),
      title: item.title,
      url: item.url ?? "",
      domain: item.domain ?? "",
      tldr: item.tldr ?? "",
      topic_tags: item.topicTags ?? [],
      score: item.relevanceScore ?? 0,
      match_type: item.matchSignals?.[0] ?? "search",
      created_at: item.createdAt,
    })),
    pagination: {
      total: payload.pagination.total,
      limit: payload.pagination.limit,
      offset: payload.pagination.offset,
      has_more: payload.pagination.hasMore,
    },
    query: payload.query,
  };
}

export function searchArticles(query: string, params?: {
  mode?: "hybrid" | "semantic" | "fts";
  limit?: number;
  offset?: number;
}): Promise<SearchResponse> {
  const q = new URLSearchParams({ q: query });
  if (params?.mode) q.set("mode", normalizeMode(params.mode));
  q.set("limit", String(params?.limit ?? 20));
  q.set("offset", String(params?.offset ?? 0));
  return apiRequest<BackendSearchPayload>(`/v1/search?${q}`).then(mapSearchResponse);
}

export function getTrendingTopics(limit = 10, days = 7): Promise<{ topics: TrendingTopic[] }> {
  return apiRequest<BackendTrendingPayload>(
    `/v1/topics/trending?limit=${limit}&days=${days}`,
  ).then((payload) => ({
    topics: payload.tags.map((tag) => ({
      tag: tag.tag,
      count: tag.count,
      recent_titles: [],
    })),
  }));
}
