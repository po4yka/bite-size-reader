import { apiRequest } from "./client";
import type { UserStats } from "../types/api";

interface BackendUserStats {
  totalSummaries: number;
  unreadCount: number;
  readCount: number;
  totalReadingTimeMin: number;
  averageReadingTimeMin: number;
  favoriteTopics: Array<{ topic: string; count: number }>;
  favoriteDomains: Array<{ domain: string; count: number }>;
  languageDistribution: Record<string, number>;
}

export function fetchUserStats(): Promise<UserStats> {
  return apiRequest<BackendUserStats>("/v1/user/stats").then((payload) => ({
    total_summaries: payload.totalSummaries,
    total_reading_time_min: payload.totalReadingTimeMin,
    summaries_this_week: 0,
    summaries_this_month: 0,
    top_topics: payload.favoriteTopics.map((topic) => ({
      tag: topic.topic,
      count: topic.count,
    })),
    top_domains: payload.favoriteDomains.map((domain) => ({
      domain: domain.domain,
      count: domain.count,
    })),
    language_distribution: Object.entries(payload.languageDistribution).map(([lang, count]) => ({
      lang,
      count,
    })),
    favorites_count: 0,
    collections_count: 0,
  }));
}
