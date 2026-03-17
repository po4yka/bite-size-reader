import { useMutation, useQuery } from "@tanstack/react-query";
import { clearCache, fetchDbInfo } from "../api/admin";
import { queryKeys } from "../api/queryKeys";

export function useDbInfo() {
  return useQuery({
    queryKey: queryKeys.admin.dbInfo,
    queryFn: fetchDbInfo,
  });
}

export function useClearCache(onSuccess?: (result: { clearedKeys: number }) => void, onError?: (err: Error) => void) {
  return useMutation({
    mutationFn: clearCache,
    onSuccess,
    onError,
  });
}
