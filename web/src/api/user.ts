import { apiRequest } from "./client";

export interface UserPreferences {
  userId: number;
  telegramUsername: string | null;
  langPreference: "auto" | "en" | "ru" | null;
  notificationSettings: Record<string, unknown> | null;
  appSettings: Record<string, unknown> | null;
}

export interface UserStats {
  totalSummaries: number;
  unreadCount: number;
  readCount: number;
  totalReadingTimeMin: number;
  averageReadingTimeMin: number;
  favoriteTopics: Array<{ topic: string; count: number }>;
  favoriteDomains: Array<{ domain: string; count: number }>;
}

export function fetchUserPreferences(): Promise<UserPreferences> {
  return apiRequest<UserPreferences>("/v1/user/preferences");
}

export function updateUserPreferences(payload: {
  lang_preference?: "auto" | "en" | "ru";
  notification_settings?: Record<string, unknown>;
  app_settings?: Record<string, unknown>;
}): Promise<{ updatedFields: string[]; updatedAt: string }> {
  return apiRequest<{ updatedFields: string[]; updatedAt: string }>("/v1/user/preferences", {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function fetchUserStats(): Promise<UserStats> {
  return apiRequest<UserStats>("/v1/user/stats");
}
