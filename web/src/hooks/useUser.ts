import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  fetchUserPreferences,
  fetchUserStats,
  updateUserPreferences,
  fetchReadingGoals,
  fetchGoalsProgress,
  createReadingGoal,
  deleteReadingGoal,
  fetchReadingStreak,
} from "../api/user";
import {
  deleteAccount,
  listSessions,
  deleteSession,
  getTelegramLinkStatus,
  beginTelegramLink,
  completeTelegramLink,
  unlinkTelegram,
} from "../api/auth";
import type { TelegramAuthForLink } from "../api/auth";
import { queryKeys } from "../api/queryKeys";
import { useAuth } from "../auth/AuthProvider";

export function useUserPreferences() {
  return useQuery({
    queryKey: queryKeys.user.preferences,
    queryFn: fetchUserPreferences,
  });
}

export function useUserStats() {
  return useQuery({
    queryKey: queryKeys.user.stats,
    queryFn: fetchUserStats,
  });
}

export function useUpdateUserPreferences(onSuccess?: () => void) {
  return useMutation({
    mutationFn: (payload: Parameters<typeof updateUserPreferences>[0]) =>
      updateUserPreferences(payload),
    onSuccess,
  });
}

export function useReadingGoals() {
  return useQuery({
    queryKey: queryKeys.user.goals.all,
    queryFn: fetchReadingGoals,
  });
}

export function useGoalsProgress() {
  return useQuery({
    queryKey: queryKeys.user.goals.progress,
    queryFn: fetchGoalsProgress,
  });
}

export function useCreateGoal() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ goalType, target, period }: { goalType: string; target: number; period: string }) =>
      createReadingGoal(goalType, target, period),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.user.goals.all });
      void queryClient.invalidateQueries({ queryKey: queryKeys.user.goals.progress });
    },
  });
}

export function useDeleteGoal() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (goalType: string) => deleteReadingGoal(goalType),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.user.goals.all });
    },
  });
}

export function useReadingStreak() {
  return useQuery({
    queryKey: queryKeys.user.streak,
    queryFn: fetchReadingStreak,
  });
}

export function useDeleteAccount() {
  const { logout } = useAuth();
  return useMutation({
    mutationFn: deleteAccount,
    onSuccess: () => {
      logout();
    },
  });
}

export function useSessions() {
  return useQuery({
    queryKey: queryKeys.auth.sessions,
    queryFn: listSessions,
  });
}

export function useDeleteSession() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (sessionId: string) => deleteSession(sessionId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.auth.sessions });
    },
  });
}

export function useTelegramLinkStatus() {
  return useQuery({
    queryKey: queryKeys.auth.telegramLink,
    queryFn: getTelegramLinkStatus,
  });
}

export function useBeginTelegramLink() {
  return useMutation({
    mutationFn: beginTelegramLink,
  });
}

export function useCompleteTelegramLink() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ nonce, telegramAuth }: { nonce: string; telegramAuth: TelegramAuthForLink }) =>
      completeTelegramLink(nonce, telegramAuth),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.auth.telegramLink });
    },
  });
}

export function useUnlinkTelegram() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: unlinkTelegram,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.auth.telegramLink });
    },
  });
}
