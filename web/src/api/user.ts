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

export interface ReadingGoal {
  goalType: string;
  target: number;
  period: string;
  currentCount: number;
  isCompleted: boolean;
}

export interface GoalProgress {
  goalType: string;
  target: number;
  current: number;
  percentage: number;
  isCompleted: boolean;
}

export interface ReadingStreak {
  currentStreak: number;
  longestStreak: number;
  todayCount: number;
  thisWeekCount: number;
  thisMonthCount: number;
  lastReadAt: string | null;
}

interface ReadingGoalsResponse {
  goals: ReadingGoal[];
}

interface GoalsProgressResponse {
  progress: GoalProgress[];
}

export async function fetchReadingGoals(): Promise<ReadingGoal[]> {
  const result = await apiRequest<ReadingGoalsResponse>("/v1/user/goals");
  return result.goals;
}

export async function fetchGoalsProgress(): Promise<GoalProgress[]> {
  const result = await apiRequest<GoalsProgressResponse>("/v1/user/goals/progress");
  return result.progress;
}

export async function createReadingGoal(
  goalType: string,
  target: number,
  period: string,
): Promise<ReadingGoal> {
  return apiRequest<ReadingGoal>("/v1/user/goals", {
    method: "POST",
    body: JSON.stringify({ goal_type: goalType, target, period }),
  });
}

export async function deleteReadingGoal(goalType: string): Promise<void> {
  await apiRequest<Record<string, never>>(`/v1/user/goals/${goalType}`, {
    method: "DELETE",
  });
}

export async function fetchReadingStreak(): Promise<ReadingStreak> {
  return apiRequest<ReadingStreak>("/v1/user/streak");
}
