import { apiRequest } from "./client";
import type { SummaryCompact, SummaryDetail, SummaryContent, PaginationInfo } from "../types/api";

interface SummaryListResponse {
  summaries: SummaryCompact[];
  pagination: PaginationInfo;
}

interface BackendPaginationInfo {
  total: number;
  limit: number;
  offset: number;
  hasMore?: boolean;
  has_more?: boolean;
}

interface BackendSummaryListItem {
  id: number;
  requestId?: number;
  request_id?: number;
  title?: string;
  domain?: string;
  url?: string;
  tldr?: string;
  summary250?: string;
  summary_250?: string;
  readingTimeMin?: number;
  estimated_reading_time_min?: number;
  topicTags?: string[];
  topic_tags?: string[];
  isRead?: boolean;
  is_read?: boolean;
  isFavorited?: boolean;
  is_favorited?: boolean;
  lang?: string;
  createdAt?: string;
  created_at?: string;
  confidence?: number;
}

interface BackendSummariesPayload {
  summaries?: BackendSummaryListItem[];
  items?: BackendSummaryListItem[];
  pagination: BackendPaginationInfo;
}

interface BackendSummaryDetailData {
  summary: {
    summary250?: string;
    summary_250?: string;
    summary1000?: string;
    summary_1000?: string;
    tldr?: string;
    keyIdeas?: string[];
    key_ideas?: string[];
    topicTags?: string[];
    topic_tags?: string[];
    entities?: {
      people?: string[];
      organizations?: string[];
      locations?: string[];
    } | null;
    estimatedReadingTimeMin?: number;
    estimated_reading_time_min?: number;
    keyStats?: Array<{ label?: string; value?: number; unit?: string | null; sourceExcerpt?: string }>;
    key_stats?: Array<{ label?: string; value?: number; unit?: string | null; source_excerpt?: string }>;
    answeredQuestions?: string[];
    answered_questions?: string[];
    readability?: { method?: string; score?: number; level?: string } | null;
    seoKeywords?: string[];
    seo_keywords?: string[];
  };
  request?: {
    id?: number | string;
    url?: string | null;
    normalizedUrl?: string | null;
    normalized_url?: string | null;
    createdAt?: string;
    created_at?: string;
    updatedAt?: string;
    updated_at?: string;
  } | null;
  source?: {
    url?: string | null;
    title?: string | null;
    domain?: string | null;
    wordCount?: number | null;
    word_count?: number | null;
  } | null;
  processing?: {
    modelUsed?: string | null;
    model_used?: string | null;
    confidence?: number | null;
  } | null;
}

interface BackendSummaryContentPayload {
  content: {
    summaryId?: number;
    summary_id?: number;
    format?: string;
    content: string;
    contentType?: string;
    content_type?: string;
  };
}

function normalizeSort(sort?: string): string | undefined {
  if (!sort) return undefined;
  if (sort === "-created_at") return "created_at_desc";
  if (sort === "created_at") return "created_at_asc";
  return sort;
}

function mapPagination(pagination: BackendPaginationInfo): PaginationInfo {
  return {
    total: pagination.total,
    limit: pagination.limit,
    offset: pagination.offset,
    has_more: Boolean(pagination.hasMore ?? pagination.has_more),
  };
}

function mapSummaryCompact(item: BackendSummaryListItem): SummaryCompact {
  return {
    id: item.id,
    request_id: String(item.requestId ?? item.request_id ?? ""),
    title: item.title ?? "Untitled",
    url: item.url ?? "",
    domain: item.domain ?? "",
    tldr: item.tldr ?? "",
    summary_250: item.summary250 ?? item.summary_250 ?? "",
    topic_tags: item.topicTags ?? item.topic_tags ?? [],
    estimated_reading_time_min:
      item.readingTimeMin ?? item.estimated_reading_time_min ?? 0,
    is_read: Boolean(item.isRead ?? item.is_read),
    is_favorite: Boolean(item.isFavorited ?? item.is_favorited),
    lang: item.lang ?? "auto",
    created_at: item.createdAt ?? item.created_at ?? "",
  };
}

function toEntities(summary: BackendSummaryDetailData["summary"]): SummaryDetail["entities"] {
  const entities = summary.entities ?? {};
  return [
    ...(entities.people ?? []).map((name) => ({ name, type: "person" })),
    ...(entities.organizations ?? []).map((name) => ({ name, type: "organization" })),
    ...(entities.locations ?? []).map((name) => ({ name, type: "location" })),
  ];
}

function toDomain(url: string): string {
  try {
    return new URL(url).hostname;
  } catch {
    return "";
  }
}

export function fetchSummaries(params: {
  is_read?: boolean;
  is_favorite?: boolean;
  is_favorited?: boolean;
  limit?: number;
  offset?: number;
  sort?: string;
} = {}): Promise<SummaryListResponse> {
  const q = new URLSearchParams();
  if (params.is_read !== undefined) q.set("is_read", String(params.is_read));
  const favorited = params.is_favorited ?? params.is_favorite;
  if (favorited !== undefined) q.set("is_favorited", String(favorited));
  q.set("limit", String(params.limit ?? 20));
  q.set("offset", String(params.offset ?? 0));
  const normalizedSort = normalizeSort(params.sort);
  if (normalizedSort) q.set("sort", normalizedSort);
  return apiRequest<BackendSummariesPayload>(`/v1/summaries?${q}`).then((payload) => {
    const rows = payload.summaries ?? payload.items ?? [];
    return {
      summaries: rows.map(mapSummaryCompact),
      pagination: mapPagination(payload.pagination),
    };
  });
}

export function fetchSummary(id: number): Promise<SummaryDetail> {
  return apiRequest<BackendSummaryDetailData>(`/v1/summaries/${id}`).then((payload) => {
    const summary = payload.summary;
    const request = payload.request ?? {};
    const source = payload.source ?? {};
    const processing = payload.processing ?? {};
    const resolvedUrl = source.url ?? request.url ?? request.normalizedUrl ?? request.normalized_url ?? "";
    const resolvedDomain = source.domain ?? toDomain(resolvedUrl);

    const keyStats = summary.keyStats ?? summary.key_stats ?? [];
    const answered = summary.answeredQuestions ?? summary.answered_questions ?? [];

    return {
      id,
      request_id: String(request.id ?? ""),
      title: source.title ?? "Untitled",
      url: resolvedUrl,
      domain: resolvedDomain,
      tldr: summary.tldr ?? "",
      summary_250: summary.summary250 ?? summary.summary_250 ?? "",
      summary_1000: summary.summary1000 ?? summary.summary_1000 ?? "",
      key_ideas: (summary.keyIdeas ?? summary.key_ideas ?? []).map((idea) => ({ idea })),
      entities: toEntities(summary),
      key_stats: keyStats.map((item) => {
        const withContext = item as { sourceExcerpt?: string; source_excerpt?: string };
        return {
          stat: [
            item.label ?? "",
            item.value != null ? `${item.value}${item.unit ? ` ${item.unit}` : ""}` : "",
          ]
            .filter(Boolean)
            .join(": "),
          context: withContext.sourceExcerpt ?? withContext.source_excerpt,
        };
      }),
      answered_questions: answered.map((question) => ({ question, answer: "" })),
      readability: summary.readability?.level ?? "",
      seo_keywords: summary.seoKeywords ?? summary.seo_keywords ?? [],
      confidence: processing.confidence ?? 0,
      source: {
        original_url: resolvedUrl,
        crawl_method: processing.modelUsed ?? processing.model_used ?? "",
        content_length: source.wordCount ?? source.word_count ?? 0,
      },
      topic_tags: summary.topicTags ?? summary.topic_tags ?? [],
      estimated_reading_time_min:
        summary.estimatedReadingTimeMin ?? summary.estimated_reading_time_min ?? 0,
      is_read: false,
      is_favorite: false,
      lang: "auto",
      created_at: request.createdAt ?? request.created_at ?? request.updatedAt ?? request.updated_at ?? "",
    };
  });
}

export function fetchSummaryContent(id: number): Promise<SummaryContent> {
  return apiRequest<BackendSummaryContentPayload>(`/v1/summaries/${id}/content`).then((payload) => {
    const content = payload.content;
    const format = content.format ?? "markdown";
    const contentType = content.contentType ?? content.content_type ?? "";
    const text = format === "text" || contentType === "text/plain" ? content.content : "";
    const markdown = format === "markdown" || contentType === "text/markdown" ? content.content : text;
    const html = contentType === "text/html" ? content.content : "";
    const baseText = (text || markdown || html).trim();

    return {
      id: content.summaryId ?? content.summary_id ?? id,
      markdown,
      html,
      text,
      word_count: baseText ? baseText.split(/\s+/).length : 0,
    };
  });
}

export function setReadStatus(
  id: number,
  isRead: boolean,
): Promise<{ is_read: boolean; updated_at: string }> {
  return apiRequest<{ isRead?: boolean; is_read?: boolean; updatedAt?: string; updated_at?: string }>(
    `/v1/summaries/${id}`,
    {
      method: "PATCH",
      body: JSON.stringify({ is_read: isRead }),
    },
  ).then((payload) => ({
    is_read: Boolean(payload.isRead ?? payload.is_read),
    updated_at: payload.updatedAt ?? payload.updated_at ?? "",
  }));
}

export function markAsRead(id: number): Promise<{ is_read: boolean; updated_at: string }> {
  return setReadStatus(id, true);
}

export function markAsUnread(id: number): Promise<{ is_read: boolean; updated_at: string }> {
  return setReadStatus(id, false);
}

export function toggleFavorite(id: number): Promise<{ is_favorite: boolean }> {
  return apiRequest<{ isFavorited?: boolean; is_favorited?: boolean }>(
    `/v1/summaries/${id}/favorite`,
    { method: "POST" },
  ).then((payload) => ({
    is_favorite: Boolean(payload.isFavorited ?? payload.is_favorited),
  }));
}

export function deleteSummary(id: number): Promise<{ id: number; deleted_at: string }> {
  return apiRequest<{ id: number; deletedAt?: string; deleted_at?: string }>(`/v1/summaries/${id}`, {
    method: "DELETE",
  }).then((payload) => ({
    id: payload.id,
    deleted_at: payload.deletedAt ?? payload.deleted_at ?? "",
  }));
}
