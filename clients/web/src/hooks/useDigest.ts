import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  assignDigestCategory,
  bulkAssignDigestCategory,
  bulkUnsubscribeDigest,
  createDigestCategory,
  deleteDigestCategory,
  fetchDigestChannelPosts,
  fetchDigestChannels,
  fetchDigestHistory,
  fetchDigestPreferences,
  listDigestCategories,
  resolveDigestChannel,
  subscribeDigestChannel,
  triggerDigestNow,
  triggerSingleChannelDigest,
  unsubscribeDigestChannel,
  updateDigestCategory,
  updateDigestPreferences,
} from "../api/digest";
import { queryKeys } from "../api/queryKeys";
import {
  createCustomDigest,
  getCustomDigest,
  listCustomDigests,
} from "../api/customDigest";
import type { CreateCustomDigestParams } from "../api/customDigest";

const HISTORY_PAGE_SIZE = 20;

export function useDigestChannels() {
  return useQuery({
    queryKey: queryKeys.digest.channels,
    queryFn: fetchDigestChannels,
  });
}

export function useDigestCategories() {
  return useQuery({
    queryKey: queryKeys.digest.categories,
    queryFn: listDigestCategories,
  });
}

export function useDigestPreferences() {
  return useQuery({
    queryKey: queryKeys.digest.preferences,
    queryFn: fetchDigestPreferences,
  });
}

export function useDigestHistory(page: number) {
  return useQuery({
    queryKey: queryKeys.digest.history(page),
    queryFn: () => fetchDigestHistory(HISTORY_PAGE_SIZE, (page - 1) * HISTORY_PAGE_SIZE),
  });
}

export { HISTORY_PAGE_SIZE };

export function useChannelPosts(username: string) {
  return useQuery({
    queryKey: queryKeys.digest.channelPosts(username),
    queryFn: () => fetchDigestChannelPosts(username),
  });
}

export function useSubscribeChannel() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (username: string) => subscribeDigestChannel(username),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.digest.channels });
    },
  });
}

export function useUnsubscribeChannel() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (username: string) => unsubscribeDigestChannel(username),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.digest.channels });
    },
  });
}

export function useBulkUnsubscribe() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (usernames: string[]) => bulkUnsubscribeDigest(usernames),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.digest.channels });
    },
  });
}

export function useAssignCategory() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ subscriptionId, categoryId }: { subscriptionId: number; categoryId: number | null }) =>
      assignDigestCategory(subscriptionId, categoryId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.digest.channels });
    },
  });
}

export function useBulkAssignCategory() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ ids, categoryId }: { ids: number[]; categoryId: number | null }) =>
      bulkAssignDigestCategory(ids, categoryId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.digest.channels });
    },
  });
}

export function useTriggerDigest() {
  return useMutation({ mutationFn: triggerDigestNow });
}

export function useTriggerSingleChannelDigest() {
  return useMutation({
    mutationFn: (username: string) => triggerSingleChannelDigest(username),
  });
}

export function useCreateCategory() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (name: string) => createDigestCategory(name),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.digest.categories });
    },
  });
}

export function useUpdateCategory() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, name }: { id: number; name: string }) => updateDigestCategory(id, name),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.digest.categories });
    },
  });
}

export function useDeleteCategory() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => deleteDigestCategory(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.digest.categories });
      void queryClient.invalidateQueries({ queryKey: queryKeys.digest.channels });
    },
  });
}

export function useUpdateDigestPreferences() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: Partial<{
      delivery_time: string;
      timezone: string;
      hours_lookback: number;
      max_posts_per_digest: number;
      min_relevance_score: number;
    }>) => updateDigestPreferences(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.digest.preferences });
    },
  });
}

export function useResolveChannel() {
  return useMutation({
    mutationFn: (username: string) => resolveDigestChannel(username),
  });
}

// --- Custom Digests ---

export function useCustomDigests(page = 1) {
  return useQuery({
    queryKey: ["digest", "custom", page] as const,
    queryFn: () => listCustomDigests(page),
  });
}

export function useCustomDigest(id: number) {
  return useQuery({
    queryKey: ["digest", "custom", id] as const,
    queryFn: () => getCustomDigest(id),
    enabled: id > 0,
  });
}

export function useCreateCustomDigest() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (params: CreateCustomDigestParams) => createCustomDigest(params),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["digest", "custom"] });
    },
  });
}
