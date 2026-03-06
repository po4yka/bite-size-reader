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

interface BackendUserPreferences {
  userId: number;
  telegramUsername?: string | null;
  langPreference?: "auto" | "en" | "ru" | null;
  notificationSettings?: Record<string, unknown> | null;
  appSettings?: Record<string, unknown> | null;
}

interface BackendPreferencesUpdateResult {
  updatedFields: string[];
  updatedAt: string;
}

export interface UserPreferencesData {
  user_id: number;
  telegram_username: string | null;
  lang_preference: "auto" | "en" | "ru" | null;
  notification_settings: Record<string, unknown> | null;
  app_settings: Record<string, unknown> | null;
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

export function fetchUserPreferences(): Promise<UserPreferencesData> {
  return apiRequest<BackendUserPreferences>("/v1/user/preferences").then((payload) => ({
    user_id: payload.userId,
    telegram_username: payload.telegramUsername ?? null,
    lang_preference: payload.langPreference ?? null,
    notification_settings: payload.notificationSettings ?? null,
    app_settings: payload.appSettings ?? null,
  }));
}

export function updateUserPreferences(prefs: {
  lang_preference?: "auto" | "en" | "ru";
  notification_settings?: Record<string, unknown>;
  app_settings?: Record<string, unknown>;
}): Promise<{ updated_fields: string[]; updated_at: string }> {
  return apiRequest<BackendPreferencesUpdateResult>("/v1/user/preferences", {
    method: "PATCH",
    body: JSON.stringify(prefs),
  }).then((payload) => ({
    updated_fields: payload.updatedFields,
    updated_at: payload.updatedAt,
  }));
}
