import { apiRequest } from "./client";
import type { PaginationInfo, SearchResult } from "./types";

interface SearchPayload {
  results: Array<{
    summaryId?: number;
    summary_id?: number;
    requestId?: number;
    request_id?: number;
    title: string;
    url?: string | null;
    domain?: string | null;
    tldr?: string | null;
    topicTags?: string[] | null;
    topic_tags?: string[] | null;
    relevanceScore?: number | null;
    createdAt?: string;
    created_at?: string;
  }>;
  pagination: {
    total: number;
    limit: number;
    offset: number;
    hasMore?: boolean;
    has_more?: boolean;
  };
}

function mapPagination(raw: SearchPayload["pagination"]): PaginationInfo {
  return {
    total: raw.total,
    limit: raw.limit,
    offset: raw.offset,
    hasMore: Boolean(raw.hasMore ?? raw.has_more),
  };
}

function mapSearchRow(row: SearchPayload["results"][number]): SearchResult {
  return {
    id: Number(row.summaryId ?? row.summary_id ?? 0),
    requestId: String(row.requestId ?? row.request_id ?? ""),
    title: row.title,
    url: row.url ?? "",
    domain: row.domain ?? "",
    tldr: row.tldr ?? "",
    topicTags: row.topicTags ?? row.topic_tags ?? [],
    score: Number(row.relevanceScore ?? 0),
    createdAt: row.createdAt ?? row.created_at ?? "",
  };
}

export async function searchSummaries(query: string, params: {
  offset?: number;
  limit?: number;
  tags?: string[];
  domains?: string[];
  language?: string;
} = {}): Promise<{ results: SearchResult[]; pagination: PaginationInfo }> {
  const q = new URLSearchParams({ q: query });
  q.set("limit", String(params.limit ?? 20));
  q.set("offset", String(params.offset ?? 0));
  if (params.language) q.set("language", params.language);
  for (const tag of params.tags ?? []) q.append("tags", tag);
  for (const domain of params.domains ?? []) q.append("domains", domain);

  const data = await apiRequest<SearchPayload>(`/v1/search?${q.toString()}`);
  return {
    results: data.results.map(mapSearchRow),
    pagination: mapPagination(data.pagination),
  };
}

export async function fetchTrendingTopics(limit = 12): Promise<Array<{ tag: string; count: number }>> {
  const data = await apiRequest<{ tags: Array<{ tag: string; count: number }> }>(
    `/v1/topics/trending?limit=${limit}&days=7`,
  );
  return data.tags;
}
