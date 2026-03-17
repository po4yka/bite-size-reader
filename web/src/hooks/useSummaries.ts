import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  fetchSummaries,
  fetchSummary,
  fetchSummaryContent,
  generateSummaryAudio,
  markSummaryRead,
  toggleSummaryFavorite,
} from "../api/summaries";
import { queryKeys } from "../api/queryKeys";

export interface SummariesListParams {
  limit?: number;
  offset?: number;
  isRead?: boolean;
  isFavorited?: boolean;
  sort?: "created_at_desc" | "created_at_asc";
}

export function useSummariesList(params: SummariesListParams = {}) {
  return useQuery({
    queryKey: queryKeys.summaries.list(params as Record<string, unknown>),
    queryFn: () => fetchSummaries(params),
  });
}

export function useSummaryDetail(summaryId: number) {
  return useQuery({
    queryKey: queryKeys.summaries.detail(summaryId),
    queryFn: () => fetchSummary(summaryId),
    enabled: Number.isFinite(summaryId) && summaryId > 0,
  });
}

export function useSummaryContent(summaryId: number, enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.summaries.content(summaryId),
    queryFn: () => fetchSummaryContent(summaryId),
    enabled: enabled && Number.isFinite(summaryId) && summaryId > 0,
  });
}

export function useMarkRead(summaryId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => markSummaryRead(summaryId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.summaries.all });
    },
  });
}

/** Pass summaryId to pre-bind; omit to receive it at call-site via mutate(summaryId). */
export function useToggleFavorite(summaryId?: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id?: number) => toggleSummaryFavorite((id ?? summaryId)!),
    onSuccess: (_, id) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.summaries.all });
      const resolvedId = id ?? summaryId;
      if (resolvedId != null) {
        void queryClient.invalidateQueries({ queryKey: queryKeys.summaries.detail(resolvedId) });
      }
    },
  });
}

export function useGenerateAudio() {
  return useMutation({
    mutationFn: ({ summaryId, sourceField }: { summaryId: number; sourceField?: string }) =>
      generateSummaryAudio(summaryId, sourceField),
  });
}
