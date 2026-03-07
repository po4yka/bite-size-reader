export interface PaginationInfo {
  total: number;
  limit: number;
  offset: number;
  hasMore: boolean;
}

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
