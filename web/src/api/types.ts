/**
 * API domain types for the web frontend.
 *
 * Types are aligned with the OpenAPI spec at docs/openapi/mobile_api.yaml,
 * accessible via components["schemas"] in ./generated.ts.
 *
 * Where the generated schema matches exactly, types are re-exported directly.
 * Where there are minor shape differences (e.g. requestId: string vs number,
 * Collection missing serverVersion/isShared), manual types are kept with a
 * reference comment pointing to the corresponding generated schema.
 */
import type { components } from "./generated";

// ---------------------------------------------------------------------------
// Pagination — re-exported from generated (exact match)
// spec: components["schemas"]["Pagination"]
// ---------------------------------------------------------------------------
export type PaginationInfo = components["schemas"]["Pagination"];

// ---------------------------------------------------------------------------
// Summaries
// spec: components["schemas"]["SummaryListItem"] (requestId is number in spec;
// kept as string here for backward compat with existing component code)
// ---------------------------------------------------------------------------
export interface SummaryCompact {
  id: number;
  requestId: string;
  title: string;
  url: string;
  domain: string;
  tldr: string;
  summary250: string;
  topicTags: string[];
  readingTimeMin: number;
  isRead: boolean;
  isFavorited: boolean;
  lang: string;
  createdAt: string;
}

export interface SummaryDetail {
  id: number;
  requestId: string;
  title: string;
  url: string;
  domain: string;
  tldr: string;
  summary250: string;
  summary1000: string;
  keyIdeas: string[];
  entities: Array<{ name: string; type: string }>;
  topicTags: string[];
  readingTimeMin: number;
  confidence: number;
  hallucinationRisk: string;
  keyStats: Array<{ label: string; value: string; sourceExcerpt?: string }>;
}

// ---------------------------------------------------------------------------
// Collections
// spec: components["schemas"]["Collection"] (includes additional fields:
// createdAt, updatedAt, serverVersion, isShared not used by current UI)
// ---------------------------------------------------------------------------
export interface Collection {
  id: number;
  name: string;
  description?: string | null;
  parentId: number | null;
  position?: number | null;
  itemCount: number;
  children?: Collection[];
}

export interface CollectionItem {
  id: number;
  collectionId: number;
  summaryId: number;
  position: number;
  createdAt: string;
  title?: string;
  domain?: string;
}

// ---------------------------------------------------------------------------
// Search
// spec: components["schemas"]["SearchResultItem"] (snake_case — normalizeKeys
// converts to camelCase at runtime; manual type reflects runtime shape)
// ---------------------------------------------------------------------------
export interface SearchResult {
  id: number;
  requestId: string;
  title: string;
  url: string;
  domain: string;
  snippet?: string;
  tldr: string;
  topicTags: string[];
  score: number;
  createdAt: string;
  publishedAt?: string;
  isRead?: boolean;
  matchSignals?: string[];
  matchExplanation?: string;
  scoreBreakdown?: Record<string, number>;
}

export interface SearchFacet {
  value: string;
  count: number;
}

export interface SearchFacets {
  domains: SearchFacet[];
  languages: SearchFacet[];
  tags: SearchFacet[];
  readStates: SearchFacet[];
}

export interface SearchResponse {
  results: SearchResult[];
  pagination: PaginationInfo;
  query: string;
  intent?: string | null;
  mode?: string | null;
  facets?: SearchFacets;
}

// ---------------------------------------------------------------------------
// Requests
// spec: components["schemas"]["RequestStatusData"] (uses progress.percentage
// instead of progressPct; kept as-is for existing component compatibility)
// ---------------------------------------------------------------------------
export interface RequestStatus {
  requestId: string;
  status: "pending" | "crawling" | "processing" | "completed" | "failed";
  progressPct: number;
  summaryId: number | null;
  errorMessage: string | null;
  queuePosition?: number | null;
  estimatedSecondsRemaining?: number | null;
  canRetry?: boolean;
  retryable?: boolean | null;
  correlationId?: string | null;
  updatedAt?: string | null;
  errorType?: string | null;
  errorReasonCode?: string | null;
}
