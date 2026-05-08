import { act } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { createTestQueryClient, renderHookWithProviders } from "../testing/render";
import { queryKeys } from "../api/queryKeys";
import { useDuplicateCheck, useRequestStatus, useRetryRequest } from "./useRequests";

vi.mock("../api/requests", () => ({
  checkDuplicate: vi.fn(),
  fetchRequestStatus: vi.fn(),
  retryRequest: vi.fn(),
  submitForward: vi.fn(),
  submitUrl: vi.fn(),
}));

const { checkDuplicate, fetchRequestStatus, retryRequest } = await import("../api/requests");
const checkDupMock = vi.mocked(checkDuplicate);
const fetchStatusMock = vi.mocked(fetchRequestStatus);
const retryRequestMock = vi.mocked(retryRequest);

describe("useRequests hooks", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("useDuplicateCheck", () => {
    it("does not fetch when url is empty", () => {
      renderHookWithProviders(() => useDuplicateCheck("", true));
      expect(checkDupMock).not.toHaveBeenCalled();
    });

    it("does not fetch when enabled is false", () => {
      renderHookWithProviders(() => useDuplicateCheck("https://example.com", false));
      expect(checkDupMock).not.toHaveBeenCalled();
    });

    it("fetches when url is non-empty and enabled", () => {
      checkDupMock.mockResolvedValueOnce({} as Awaited<ReturnType<typeof checkDuplicate>>);
      renderHookWithProviders(() => useDuplicateCheck("https://example.com", true));
      expect(checkDupMock).toHaveBeenCalledWith("https://example.com");
    });
  });

  describe("useRequestStatus", () => {
    it("does not fetch when requestId is null", () => {
      renderHookWithProviders(() => useRequestStatus(null, false));
      expect(fetchStatusMock).not.toHaveBeenCalled();
    });

    it("does not fetch when paused is true", () => {
      renderHookWithProviders(() => useRequestStatus("req-1", true));
      expect(fetchStatusMock).not.toHaveBeenCalled();
    });

    it("fetches when requestId is set and not paused", () => {
      fetchStatusMock.mockResolvedValueOnce({} as Awaited<ReturnType<typeof fetchRequestStatus>>);
      renderHookWithProviders(() => useRequestStatus("req-1", false));
      expect(fetchStatusMock).toHaveBeenCalledWith("req-1");
    });
  });

  describe("useRetryRequest", () => {
    it("invalidates the old request's status cache entry after a successful retry", async () => {
      const queryClient = createTestQueryClient();

      // Pre-seed a stale "failed" status entry for the original request in the cache.
      queryClient.setQueryData(queryKeys.requests.status("42"), {
        requestId: "42",
        status: "failed",
        progressPct: 0,
        summaryId: null,
        errorMessage: "scrape timeout",
        queuePosition: null,
        estimatedSecondsRemaining: null,
        canRetry: true,
        retryable: true,
        correlationId: "corr-42",
        updatedAt: null,
        errorType: null,
        errorReasonCode: null,
      });

      retryRequestMock.mockResolvedValueOnce({
        kind: "queued",
        requestId: "99",
        status: "pending",
        correlationId: "corr-42-retry-1",
        estimatedWaitSeconds: null,
        createdAt: "2026-05-06T10:00:00Z",
      });

      const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

      const { result } = renderHookWithProviders(() => useRetryRequest(), { queryClient });

      await act(async () => {
        result.current.mutate("42");
        // Let the microtask queue drain so onSuccess fires.
        await new Promise((resolve) => setTimeout(resolve, 0));
      });

      expect(retryRequestMock).toHaveBeenCalledWith("42");
      expect(invalidateSpy).toHaveBeenCalledWith(
        expect.objectContaining({ queryKey: queryKeys.requests.status("42") }),
      );
    });
  });
});
