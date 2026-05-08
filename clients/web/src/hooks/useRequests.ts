import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  checkDuplicate,
  fetchRequestStatus,
  retryRequest,
  submitForward,
  submitUrl,
} from "../api/requests";
import type { ForwardMetadata } from "../api/requests";
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
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (requestId: string) => retryRequest(requestId),
    onSuccess: (_data, requestId) => {
      // The backend creates a NEW request for each retry (correlation_id="<old>-retry-N").
      // The original request stays in "failed" state permanently, so its cached status
      // entry is now stale. Invalidate it so any subscriber re-fetches the terminal state
      // rather than continuing to see outdated in-progress data.
      void queryClient.invalidateQueries({ queryKey: queryKeys.requests.status(requestId) });
    },
  });
}

export function useSubmitForward() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      contentText,
      forwardMetadata,
      langPreference,
    }: {
      contentText: string;
      forwardMetadata?: ForwardMetadata;
      langPreference?: string;
    }) => submitForward(contentText, forwardMetadata, langPreference),
    onSuccess: (data) => {
      if (data.kind === "queued") {
        void queryClient.invalidateQueries({ queryKey: queryKeys.requests.status(data.requestId) });
      }
    },
  });
}
