import { useMutation, useQuery } from "@tanstack/react-query";
import { fetchUserPreferences, fetchUserStats, updateUserPreferences } from "../api/user";
import { queryKeys } from "../api/queryKeys";

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
