// Shared TypeScript interfaces for API responses

export interface SummaryCompact {
  id: number;
  request_id: string;
  title: string;
  url: string;
  domain: string;
  tldr: string;
  summary_250: string;
  topic_tags: string[];
  estimated_reading_time_min: number;
  is_read: boolean;
  is_favorite: boolean;
  lang: string;
  created_at: string;
  source_type?: string;
}

export interface SummaryDetail extends SummaryCompact {
  summary_1000: string;
  key_ideas: Array<{ idea: string; relevance?: string }>;
  entities: Array<{ name: string; type: string; context?: string }>;
  key_stats: Array<{ stat: string; context?: string }>;
  answered_questions: Array<{ question: string; answer: string }>;
  readability: string;
  seo_keywords: string[];
  confidence: number;
  source: {
    original_url: string;
    crawl_method: string;
    content_length: number;
  };
}

export interface SummaryContent {
  id: number;
  markdown: string;
  html: string;
  text: string;
  word_count: number;
}

export interface SearchResult {
  id: number;
  request_id: string;
  title: string;
  url: string;
  domain: string;
  tldr: string;
  topic_tags: string[];
  score: number;
  match_type: string;
  created_at: string;
}

export interface TrendingTopic {
  tag: string;
  count: number;
  recent_titles: string[];
}

export interface Collection {
  id: number;
  name: string;
  parent_id: number | null;
  item_count: number;
  children_count: number;
  created_at: string;
  updated_at: string;
}

export interface CollectionItem {
  id: number;
  collection_id: number;
  summary_id: number;
  title: string;
  url: string;
  domain: string;
  tldr: string;
  topic_tags: string[];
  added_at: string;
  position: number;
}

export interface UserStats {
  total_summaries: number;
  total_reading_time_min: number;
  summaries_this_week: number;
  summaries_this_month: number;
  top_topics: Array<{ tag: string; count: number }>;
  top_domains: Array<{ domain: string; count: number }>;
  language_distribution: Array<{ lang: string; count: number }>;
  favorites_count: number;
  collections_count: number;
}

export interface UserPreferences {
  preferred_lang: string;
  notification_enabled: boolean;
  theme: string;
}

export interface RequestStatus {
  id: string;
  status: "pending" | "crawling" | "processing" | "completed" | "failed";
  progress_pct: number;
  summary_id: number | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface PaginationInfo {
  total: number;
  limit: number;
  offset: number;
  has_more: boolean;
}
