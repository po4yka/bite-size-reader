/**
 * API domain types for the web frontend.
 *
 * Types are aligned with the OpenAPI spec at docs/openapi/mobile_api.yaml,
 * accessible via components["schemas"] in ./generated.ts.
 *
 * Where the generated schema matches exactly, types are re-exported directly.
 * Where there are minor shape differences (see CONTRACT GAPS below), manual
 * types are kept with a reference comment pointing to the generated schema.
 *
 * CONTRACT GAPS (fields present in hand-written types but absent or differently
 * typed in the generated schema — each gap blocks full derivation):
 *
 * 1. SummaryCompact.requestId: hand-written type used `string`; generated
 *    SummaryListItem has `requestId: number`. The mapper in summaries.ts
 *    calls String() so runtime is fine, but the type now reflects the spec.
 *    CONTRACT GAP: existing callers that relied on `requestId: string` will
 *    need updating if they compare against string literals.
 *
 * 2. SummaryDetail: no flat generated schema exists. The detail endpoint
 *    returns SummaryDetailData (nested: .summary / .request / .source /
 *    .processing). CONTRACT GAP: no single generated schema covers the
 *    flattened SummaryDetail shape — kept as manual type.
 *
 * 3. RequestStatus.progressPct: absent from RequestStatusData (schema uses
 *    progress.percentage nested object). CONTRACT GAP: kept as manual type.
 *
 * 4. RequestStatus.summaryId: absent from RequestStatusData. The frontend
 *    resolves it via a separate /v1/requests/{id} call. CONTRACT GAP.
 */
import type { components } from "./generated";

// ---------------------------------------------------------------------------
// Pagination — re-exported from generated (exact match)
// spec: components["schemas"]["Pagination"]
// ---------------------------------------------------------------------------
export type PaginationInfo = components["schemas"]["Pagination"];

// ---------------------------------------------------------------------------
// Summaries — derived from generated schema
// spec: components["schemas"]["SummaryListItem"]
//
// NOTE CONTRACT GAP #1: requestId is number in the generated schema (matches
// the spec). The previous hand-written type used string for backward compat;
// mapSummaryCompact() in summaries.ts calls String() so runtime is unchanged.
// ---------------------------------------------------------------------------
export type SummaryCompact = components["schemas"]["SummaryListItem"];

// ---------------------------------------------------------------------------
// SummaryDetail — manual type (no flat generated equivalent)
// spec: components["schemas"]["SummaryDetailData"] (nested envelope)
//
// NOTE CONTRACT GAP #2: SummaryDetailData nests fields under .summary /
// .request / .source / .processing sub-objects. This flat shape is a
// frontend-specific projection; full derivation requires a mapped type that
// would be harder to maintain than the manual type.
// ---------------------------------------------------------------------------
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
  readingProgress?: number;
  lastReadOffset?: number;
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
  collectionType?: "manual" | "smart";
  queryConditions?: Array<{ type: string; operator: string; value: unknown }>;
  queryMatchMode?: "all" | "any";
  lastEvaluatedAt?: string | null;
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
// Highlights
// spec: POST/GET /v1/summaries/{id}/highlights
// ---------------------------------------------------------------------------
export interface Highlight {
  id: string;
  text: string;
  startOffset: number;
  endOffset: number;
  color: string | null;
  note: string | null;
  createdAt: string;
  updatedAt: string;
}

// ---------------------------------------------------------------------------
// Requests — manual type (generated schema has different shape)
// spec: components["schemas"]["RequestStatusData"]
//
// NOTE CONTRACT GAP #3: RequestStatusData uses progress.percentage (nested)
// but the frontend projects it to a flat progressPct field.
// NOTE CONTRACT GAP #4: RequestStatusData has no summaryId field; the
// frontend resolves it via a separate GET /v1/requests/{id} call and injects
// it at runtime. Full derivation from the generated schema would require
// post-processing that belongs in the mapper, not the type.
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
