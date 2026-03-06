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

interface BackendRelatedSummary {
  summary_id: number;
  title: string;
  tldr: string;
  created_at: string;
}

interface BackendRelatedTopicsPayload {
  tag: string;
  summaries: BackendRelatedSummary[];
  pagination: {
    total: number;
    limit: number;
    offset: number;
    has_more: boolean;
  };
}

interface BackendTrendingTopic {
  tag: string;
  count: number;
}

interface BackendTrendingPayload {
  tags: BackendTrendingTopic[];
}

export interface SearchInsights {
  period_days: number;
  window: {
    start: string;
    end: string;
  };
  topic_trends: Array<{
    tag: string;
    count: number;
    prev_count: number;
    trend_delta: number;
    trend_score: number;
  }>;
  rising_entities: Array<{ entity: string; count: number }>;
  source_diversity: {
    unique_domains: number;
    top_domains: Array<{ domain: string; count: number }>;
    shannon_entropy: number;
  };
  language_mix: {
    total: number;
    languages: Array<{ language: string; count: number; ratio: number }>;
  };
  coverage_gaps: Array<{
    term: string;
    mentions: number;
    tag_coverage: number;
    gap_score: number;
  }>;
}

export interface RelatedTopicSummary {
  summary_id: number;
  title: string;
  tldr: string;
  created_at: string;
}

function normalizeMode(mode: "hybrid" | "semantic" | "fts"): "hybrid" | "semantic" | "keyword" {
  if (mode === "fts") return "keyword";
  return mode;
}

function appendCommonSearchFilters(
  q: URLSearchParams,
  params?: {
    language?: string;
    tags?: string[];
    domains?: string[];
    start_date?: string;
    end_date?: string;
    is_read?: boolean;
    is_favorited?: boolean;
    min_similarity?: number;
  },
): void {
  if (!params) return;
  if (params.language) q.set("language", params.language);
  for (const tag of params.tags ?? []) q.append("tags", tag);
  for (const domain of params.domains ?? []) q.append("domains", domain);
  if (params.start_date) q.set("start_date", params.start_date);
  if (params.end_date) q.set("end_date", params.end_date);
  if (params.is_read !== undefined) q.set("is_read", String(params.is_read));
  if (params.is_favorited !== undefined) q.set("is_favorited", String(params.is_favorited));
  if (params.min_similarity !== undefined) q.set("min_similarity", String(params.min_similarity));
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
  language?: string;
  tags?: string[];
  domains?: string[];
  start_date?: string;
  end_date?: string;
  is_read?: boolean;
  is_favorited?: boolean;
  min_similarity?: number;
}): Promise<SearchResponse> {
  const q = new URLSearchParams({ q: query });
  if (params?.mode) q.set("mode", normalizeMode(params.mode));
  q.set("limit", String(params?.limit ?? 20));
  q.set("offset", String(params?.offset ?? 0));
  appendCommonSearchFilters(q, params);
  return apiRequest<BackendSearchPayload>(`/v1/search?${q}`).then(mapSearchResponse);
}

export function searchArticlesSemantic(query: string, params?: {
  limit?: number;
  offset?: number;
  language?: string;
  tags?: string[];
  domains?: string[];
  start_date?: string;
  end_date?: string;
  is_read?: boolean;
  is_favorited?: boolean;
  min_similarity?: number;
  user_scope?: string;
}): Promise<SearchResponse> {
  const q = new URLSearchParams({ q: query });
  q.set("limit", String(params?.limit ?? 20));
  q.set("offset", String(params?.offset ?? 0));
  appendCommonSearchFilters(q, params);
  if (params?.user_scope) q.set("user_scope", params.user_scope);
  return apiRequest<BackendSearchPayload>(`/v1/search/semantic?${q}`).then(mapSearchResponse);
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

export function fetchSearchInsights(days = 30, limit = 20): Promise<SearchInsights> {
  return apiRequest<SearchInsights>(`/v1/search/insights?days=${days}&limit=${limit}`);
}

export function getRelatedTopicSummaries(
  tag: string,
  limit = 20,
  offset = 0,
): Promise<{ tag: string; summaries: RelatedTopicSummary[]; pagination: PaginationInfo }> {
  const encodedTag = encodeURIComponent(tag);
  return apiRequest<BackendRelatedTopicsPayload>(
    `/v1/topics/related?tag=${encodedTag}&limit=${limit}&offset=${offset}`,
  ).then((payload) => ({
    tag: payload.tag,
    summaries: payload.summaries,
    pagination: {
      total: payload.pagination.total,
      limit: payload.pagination.limit,
      offset: payload.pagination.offset,
      has_more: payload.pagination.has_more,
    },
  }));
}
