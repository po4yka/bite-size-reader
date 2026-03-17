import { useQuery } from "@tanstack/react-query";
import { fetchTrendingTopics, searchSummaries } from "../api/search";
import type { SearchParams } from "../api/search";
import { queryKeys } from "../api/queryKeys";

export function useSearchResults(query: string, params: SearchParams = {}, enabled = true) {
  return useQuery({
    queryKey: queryKeys.search.results({ query, ...params } as Record<string, unknown>),
    queryFn: () => searchSummaries(query, params),
    enabled: enabled && query.trim().length > 1,
  });
}

export function useTrendingTopics(limit = 20) {
  return useQuery({
    queryKey: queryKeys.search.trending,
    queryFn: () => fetchTrendingTopics(limit),
  });
}
