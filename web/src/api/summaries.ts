import { apiRequest } from "./client";
import type { PaginationInfo, SummaryCompact, SummaryDetail } from "./types";
import { config } from "../lib/config";

interface SummariesPayload {
  summaries?: Array<Record<string, unknown>>;
  pagination: {
    total: number;
    limit: number;
    offset: number;
    hasMore: boolean;
  };
}

function mapSummaryCompact(raw: Record<string, unknown>): SummaryCompact {
  return {
    id: Number(raw.id ?? 0),
    requestId: String(raw.requestId ?? ""),
    title: String(raw.title ?? "Untitled"),
    url: String(raw.url ?? ""),
    domain: String(raw.domain ?? ""),
    tldr: String(raw.tldr ?? ""),
    summary250: String(raw.summary250 ?? ""),
    topicTags: (raw.topicTags as string[] | undefined) ?? [],
    readingTimeMin: Number(raw.readingTimeMin ?? raw.estimatedReadingTimeMin ?? 0),
    isRead: Boolean(raw.isRead),
    isFavorited: Boolean(raw.isFavorited),
    lang: String(raw.lang ?? "auto"),
    createdAt: String(raw.createdAt ?? ""),
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
  return {
    summaries: (data.summaries ?? []).map(mapSummaryCompact),
    pagination: data.pagination,
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

export interface AudioGenerationResponse {
  summaryId: number;
  status: string;
  charCount: number | null;
  fileSizeBytes: number | null;
  latencyMs: number | null;
  error: string | null;
}

export async function generateSummaryAudio(
  summaryId: number,
  sourceField: string = "summary_1000",
): Promise<AudioGenerationResponse> {
  const query = new URLSearchParams({ source_field: sourceField });
  return apiRequest<AudioGenerationResponse>(`/v1/summaries/${summaryId}/audio?${query.toString()}`, {
    method: "POST",
  });
}

export function getSummaryAudioUrl(summaryId: number): string {
  if (!Number.isFinite(summaryId) || summaryId <= 0) {
    throw new Error(`getSummaryAudioUrl: invalid summaryId ${summaryId}`);
  }
  const base = config.apiBaseUrl;
  return `${base}/v1/summaries/${summaryId}/audio`;
}

export async function toggleSummaryFavorite(summaryId: number): Promise<{ isFavorited: boolean }> {
  const data = await apiRequest<{ isFavorited: boolean }>(`/v1/summaries/${summaryId}/favorite`, {
    method: "POST",
  });
  return { isFavorited: Boolean(data.isFavorited) };
}

export async function saveReadingPosition(
  summaryId: number,
  progress: number,
  lastReadOffset: number,
): Promise<{ id: number; progress: number; lastReadOffset: number }> {
  return apiRequest(`/v1/summaries/${summaryId}/reading-position`, {
    method: "PATCH",
    body: JSON.stringify({ progress, last_read_offset: lastReadOffset }),
  });
}

interface RecommendationsData {
  recommendations: SummaryCompact[];
  reason: string;
  count: number;
}

export async function fetchRecommendations(limit = 10): Promise<RecommendationsData> {
  return apiRequest<RecommendationsData>(`/v1/summaries/recommendations?limit=${limit}`);
}

export async function exportSummaryPdf(summaryId: number): Promise<void> {
  const token = localStorage.getItem("access_token");
  const headers: Record<string, string> = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const response = await fetch(`/v1/summaries/${summaryId}/export?format=pdf`, { headers });
  if (!response.ok) throw new Error(`Export failed: ${response.status}`);

  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `summary-${summaryId}.pdf`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
