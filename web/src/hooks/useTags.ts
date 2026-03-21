import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  attachTags,
  createTag,
  deleteTag,
  detachTag,
  fetchTags,
  mergeTags,
  updateTag,
} from "../api/tags";
import { queryKeys } from "../api/queryKeys";

export function useTags() {
  return useQuery({
    queryKey: queryKeys.tags.list(),
    queryFn: fetchTags,
  });
}

export function useCreateTag() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ name, color }: { name: string; color?: string }) =>
      createTag(name, color),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.tags.all });
    },
  });
}

export function useUpdateTag() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ tagId, payload }: { tagId: number; payload: { name?: string; color?: string | null } }) =>
      updateTag(tagId, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.tags.all });
    },
  });
}

export function useDeleteTag() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (tagId: number) => deleteTag(tagId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.tags.all });
    },
  });
}

export function useMergeTags() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ sourceTagIds, targetTagId }: { sourceTagIds: number[]; targetTagId: number }) =>
      mergeTags(sourceTagIds, targetTagId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.tags.all });
    },
  });
}

export function useAttachTags() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ summaryId, tagIds, tagNames }: { summaryId: number; tagIds?: number[]; tagNames?: string[] }) =>
      attachTags(summaryId, { tagIds, tagNames }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.tags.all });
      void queryClient.invalidateQueries({ queryKey: queryKeys.summaries.all });
    },
  });
}

export function useDetachTag() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ summaryId, tagId }: { summaryId: number; tagId: number }) =>
      detachTag(summaryId, tagId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.tags.all });
      void queryClient.invalidateQueries({ queryKey: queryKeys.summaries.all });
    },
  });
}
