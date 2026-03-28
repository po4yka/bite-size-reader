import { describe, expect, it, vi, beforeEach } from "vitest";
import { renderHookWithProviders } from "../testing/render";
import { useDuplicateCheck, useRequestStatus } from "./useRequests";

vi.mock("../api/requests", () => ({
  checkDuplicate: vi.fn(),
  fetchRequestStatus: vi.fn(),
  retryRequest: vi.fn(),
  submitForward: vi.fn(),
  submitUrl: vi.fn(),
}));

const { checkDuplicate, fetchRequestStatus } = await import("../api/requests");
const checkDupMock = vi.mocked(checkDuplicate);
const fetchStatusMock = vi.mocked(fetchRequestStatus);

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
});
