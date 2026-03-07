import { apiRequest } from "./client";
import type { PaginationInfo, SummaryCompact, SummaryDetail } from "./types";

interface SummariesPayload {
  summaries?: Array<Record<string, unknown>>;
  items?: Array<Record<string, unknown>>;
  pagination: {
    total: number;
    limit: number;
    offset: number;
    hasMore?: boolean;
    has_more?: boolean;
  };
}

function mapPagination(raw: SummariesPayload["pagination"]): PaginationInfo {
  return {
    total: raw.total,
    limit: raw.limit,
    offset: raw.offset,
    hasMore: Boolean(raw.hasMore ?? raw.has_more),
  };
}

function mapSummaryCompact(raw: Record<string, unknown>): SummaryCompact {
  return {
    id: Number(raw.id ?? 0),
    requestId: String(raw.requestId ?? raw.request_id ?? ""),
    title: String(raw.title ?? "Untitled"),
    url: String(raw.url ?? ""),
    domain: String(raw.domain ?? ""),
    tldr: String(raw.tldr ?? ""),
    summary250: String(raw.summary250 ?? raw.summary_250 ?? ""),
    topicTags: (raw.topicTags as string[] | undefined) ?? (raw.topic_tags as string[] | undefined) ?? [],
    readingTimeMin: Number(raw.readingTimeMin ?? raw.reading_time_min ?? raw.estimatedReadingTimeMin ?? 0),
    isRead: Boolean(raw.isRead ?? raw.is_read),
    isFavorited: Boolean(raw.isFavorited ?? raw.is_favorited),
    lang: String(raw.lang ?? "auto"),
    createdAt: String(raw.createdAt ?? raw.created_at ?? ""),
  };
}

export async function fetchSummaries(params: {
  limit?: number;
  offset?: number;
  isRead?: boolean;
  isFavorited?: boolean;
  sort?: "created_at_desc" | "created_at_asc";
} = {}): Promise<{ summaries: SummaryCompact[]; pagination: PaginationInfo }> {
  const query = new URLSearchParams();
  query.set("limit", String(params.limit ?? 20));
  query.set("offset", String(params.offset ?? 0));
  if (params.isRead !== undefined) query.set("is_read", String(params.isRead));
  if (params.isFavorited !== undefined) query.set("is_favorited", String(params.isFavorited));
  if (params.sort) query.set("sort", params.sort);

  const data = await apiRequest<SummariesPayload>(`/v1/summaries?${query.toString()}`);
  const rows = data.summaries ?? data.items ?? [];
  return {
    summaries: rows.map(mapSummaryCompact),
    pagination: mapPagination(data.pagination),
  };
}

interface SummaryPayload {
  summary: {
    summary250?: string;
    summary1000?: string;
    tldr?: string;
    keyIdeas?: string[];
    topicTags?: string[];
    entities?: {
      people?: string[];
      organizations?: string[];
      locations?: string[];
    };
    estimatedReadingTimeMin?: number;
    confidence?: number;
    hallucinationRisk?: string;
    keyStats?: Array<{
      label?: string;
      value?: number | string;
      unit?: string;
      sourceExcerpt?: string;
    }>;
  };
  request: {
    id?: string;
    url?: string;
  };
  source: {
    title?: string;
    domain?: string;
    url?: string;
  };
  processing: {
    confidence?: number;
    hallucinationRisk?: string;
  };
}

function mapEntities(raw?: SummaryPayload["summary"]["entities"]): Array<{ name: string; type: string }> {
  if (!raw) return [];
  return [
    ...(raw.people ?? []).map((name) => ({ name, type: "person" })),
    ...(raw.organizations ?? []).map((name) => ({ name, type: "organization" })),
    ...(raw.locations ?? []).map((name) => ({ name, type: "location" })),
  ];
}

export async function fetchSummary(summaryId: number): Promise<SummaryDetail> {
  const data = await apiRequest<SummaryPayload>(`/v1/summaries/${summaryId}`);
  const summary = data.summary;

  return {
    id: summaryId,
    requestId: String(data.request?.id ?? ""),
    title: data.source?.title ?? "Untitled",
    url: data.source?.url ?? data.request?.url ?? "",
    domain: data.source?.domain ?? "",
    tldr: summary?.tldr ?? "",
    summary250: summary?.summary250 ?? "",
    summary1000: summary?.summary1000 ?? "",
    keyIdeas: summary?.keyIdeas ?? [],
    entities: mapEntities(summary?.entities),
    topicTags: summary?.topicTags ?? [],
    readingTimeMin: Number(summary?.estimatedReadingTimeMin ?? 0),
    confidence: Number(data.processing?.confidence ?? summary?.confidence ?? 0),
    hallucinationRisk: data.processing?.hallucinationRisk ?? summary?.hallucinationRisk ?? "unknown",
    keyStats: (summary?.keyStats ?? []).map((item) => ({
      label: item.label ?? "",
      value: `${item.value ?? ""}${item.unit ? ` ${item.unit}` : ""}`.trim(),
      sourceExcerpt: item.sourceExcerpt,
    })),
  };
}

interface ContentPayload {
  content: {
    content: string;
    format?: string;
  };
}

export async function fetchSummaryContent(summaryId: number): Promise<{ content: string; format: string }> {
  const data = await apiRequest<ContentPayload>(`/v1/summaries/${summaryId}/content?format=markdown`);
  return {
    content: data.content?.content ?? "",
    format: data.content?.format ?? "markdown",
  };
}

export function markSummaryRead(summaryId: number): Promise<{ success: boolean }> {
  return apiRequest<{ success: boolean }>(`/v1/summaries/${summaryId}`, {
    method: "PATCH",
    body: JSON.stringify({ is_read: true }),
  });
}

export async function toggleSummaryFavorite(summaryId: number): Promise<{ isFavorited: boolean }> {
  const data = await apiRequest<{ isFavorited?: boolean; is_favorited?: boolean }>(
    `/v1/summaries/${summaryId}/favorite`,
    {
      method: "POST",
    },
  );
  return { isFavorited: Boolean(data.isFavorited ?? data.is_favorited) };
}
