import { apiRequest } from "./client";
import type { PaginationInfo, SearchFacets, SearchResponse, SearchResult } from "./types";

// SearchResultItem is snake_case in the OpenAPI spec (components["schemas"]["SearchResultItem"]).
// normalizeKeys() in the HTTP client converts all keys to camelCase at runtime,
// so the interface below reflects the post-normalization runtime shape.
interface SearchPayload {
  results: Array<{
    summaryId?: number;
    requestId?: number;
    title: string;
    url?: string | null;
    domain?: string | null;
    snippet?: string | null;
    tldr?: string | null;
    topicTags?: string[] | null;
    relevanceScore?: number | null;
    createdAt?: string;
    publishedAt?: string | null;
    isRead?: boolean;
    matchSignals?: string[] | null;
    matchExplanation?: string | null;
    scoreBreakdown?: Record<string, number> | null;
  }>;
  pagination: PaginationInfo;
  query?: string;
  intent?: string | null;
  mode?: string | null;
  facets?: {
    domains?: Array<{ value: string; count: number }> | null;
    languages?: Array<{ value: string; count: number }> | null;
    tags?: Array<{ value: string; count: number }> | null;
    readStates?: Array<{ value: string; count: number }> | null;
  } | null;
}

export interface SearchParams {
  offset?: number;
  limit?: number;
  tags?: string[];
  domains?: string[];
  language?: string;
  mode?: "auto" | "keyword" | "semantic" | "hybrid";
  startDate?: string;
  endDate?: string;
  isRead?: boolean;
  isFavorited?: boolean;
  minSimilarity?: number;
}

function normalizeFacets(raw?: SearchPayload["facets"]): SearchFacets | undefined {
  if (!raw) return undefined;
  return {
    domains: raw.domains ?? [],
    languages: raw.languages ?? [],
    tags: raw.tags ?? [],
    readStates: raw.readStates ?? [],
  };
}

function mapSearchRow(row: SearchPayload["results"][number]): SearchResult {
  return {
    id: Number(row.summaryId ?? 0),
    requestId: String(row.requestId ?? ""),
    title: row.title,
    url: row.url ?? "",
    domain: row.domain ?? "",
    snippet: row.snippet ?? "",
    tldr: row.tldr ?? "",
    topicTags: row.topicTags ?? [],
    score: Number(row.relevanceScore ?? 0),
    createdAt: row.createdAt ?? "",
    publishedAt: row.publishedAt ?? "",
    isRead: Boolean(row.isRead ?? false),
    matchSignals: row.matchSignals ?? [],
    matchExplanation: row.matchExplanation ?? "",
    scoreBreakdown: row.scoreBreakdown ?? undefined,
  };
}

export function buildSearchQueryParams(query: string, params: SearchParams = {}): URLSearchParams {
  const q = new URLSearchParams({ q: query });
  q.set("limit", String(params.limit ?? 20));
  q.set("offset", String(params.offset ?? 0));
  if (params.mode) q.set("mode", params.mode);
  if (params.language) q.set("language", params.language);
  if (params.startDate) q.set("start_date", params.startDate);
  if (params.endDate) q.set("end_date", params.endDate);
  if (params.isRead != null) q.set("is_read", String(params.isRead));
  if (params.isFavorited != null) q.set("is_favorited", String(params.isFavorited));
  if (params.minSimilarity != null) q.set("min_similarity", String(params.minSimilarity));
  for (const tag of params.tags ?? []) q.append("tags", tag);
  for (const domain of params.domains ?? []) q.append("domains", domain);
  return q;
}

export async function searchSummaries(query: string, params: SearchParams = {}): Promise<SearchResponse> {
  const q = buildSearchQueryParams(query, params);
  const data = await apiRequest<SearchPayload>(`/v1/search?${q.toString()}`);
  return {
    results: data.results.map(mapSearchRow),
    pagination: data.pagination,
    query: data.query ?? query,
    intent: data.intent,
    mode: data.mode,
    facets: normalizeFacets(data.facets),
  };
}

export async function fetchTrendingTopics(limit = 12): Promise<Array<{ tag: string; count: number }>> {
  const data = await apiRequest<{ tags: Array<{ tag: string; count: number }> }>(
    `/v1/topics/trending?limit=${limit}&days=7`,
  );
  return data.tags;
}
