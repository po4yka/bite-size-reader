import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  fetchFeedItems,
  fetchRSSSubscriptions,
  importOPML,
  refreshFeed,
  subscribeToFeed,
  unsubscribeFromFeed,
} from "../api/rss";
import { queryKeys } from "../api/queryKeys";

export function useRSSSubscriptions() {
  return useQuery({
    queryKey: queryKeys.rss.subscriptions(),
    queryFn: fetchRSSSubscriptions,
  });
}

export function useSubscribeToFeed() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ url, categoryId }: { url: string; categoryId?: number }) =>
      subscribeToFeed(url, categoryId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.rss.all });
    },
  });
}

export function useUnsubscribeFromFeed() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (subscriptionId: number) => unsubscribeFromFeed(subscriptionId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.rss.all });
    },
  });
}

export function useFeedItems(feedId: number | null) {
  return useQuery({
    queryKey: queryKeys.rss.items(feedId ?? 0),
    queryFn: () => fetchFeedItems(feedId ?? 0),
    enabled: feedId != null && feedId > 0,
  });
}

export function useRefreshFeed() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (feedId: number) => refreshFeed(feedId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.rss.all });
    },
  });
}

export function useImportOPML() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => importOPML(file),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.rss.all });
    },
  });
}
