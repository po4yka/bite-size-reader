import { useMutation, useQuery } from "@tanstack/react-query";
import { checkDuplicate, fetchRequestStatus, retryRequest, submitUrl } from "../api/requests";
import { queryKeys } from "../api/queryKeys";

const POLL_INTERVAL_MS = 2500;

function isTerminalStatus(status: string): boolean {
  return status === "completed" || status === "failed";
}

export function useDuplicateCheck(url: string, enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.requests.duplicateCheck(url),
    queryFn: () => checkDuplicate(url),
    enabled: enabled && url.length > 0,
  });
}

export function useRequestStatus(requestId: string | null, paused: boolean) {
  return useQuery({
    queryKey: requestId ? queryKeys.requests.status(requestId) : (["requests", "status", null] as const),
    queryFn: () => fetchRequestStatus(requestId ?? ""),
    enabled: Boolean(requestId) && !paused,
    retry: 2,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (!status) return POLL_INTERVAL_MS;
      return isTerminalStatus(status) ? false : POLL_INTERVAL_MS;
    },
  });
}

export function useSubmitUrl() {
  return useMutation({
    mutationFn: (payload: { inputUrl: string; langPreference: "auto" | "en" | "ru" }) =>
      submitUrl(payload.inputUrl, payload.langPreference),
  });
}

export function useRetryRequest() {
  return useMutation({
    mutationFn: (requestId: string) => retryRequest(requestId),
  });
}
