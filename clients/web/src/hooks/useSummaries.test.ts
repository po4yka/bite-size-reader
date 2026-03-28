import { describe, expect, it, vi, beforeEach } from "vitest";
import { waitFor } from "@testing-library/react";
import { renderHookWithProviders } from "../testing/render";
import { useSummariesList, useSummaryDetail, useSummaryContent } from "./useSummaries";

vi.mock("../api/summaries", () => ({
  fetchSummaries: vi.fn(),
  fetchSummary: vi.fn(),
  fetchSummaryContent: vi.fn(),
  markSummaryRead: vi.fn(),
  toggleSummaryFavorite: vi.fn(),
  generateSummaryAudio: vi.fn(),
  saveReadingPosition: vi.fn(),
  exportSummaryPdf: vi.fn(),
  fetchRecommendations: vi.fn(),
  getSummaryAudioUrl: vi.fn(),
}));

vi.mock("../api/highlights", () => ({
  fetchHighlights: vi.fn(),
  createHighlight: vi.fn(),
  updateHighlight: vi.fn(),
  deleteHighlight: vi.fn(),
}));

const { fetchSummaries, fetchSummary, fetchSummaryContent } = await import("../api/summaries");
const fetchSummariesMock = vi.mocked(fetchSummaries);
const fetchSummaryMock = vi.mocked(fetchSummary);
const fetchSummaryContentMock = vi.mocked(fetchSummaryContent);

describe("useSummaries hooks", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("useSummariesList", () => {
    it("passes params to fetchSummaries and returns data", async () => {
      const mockData = {
        summaries: [{ id: 1, title: "Test" }],
        pagination: { total: 1, limit: 20, offset: 0, hasMore: false },
      };
      fetchSummariesMock.mockResolvedValueOnce(mockData as ReturnType<typeof fetchSummaries> extends Promise<infer T> ? T : never);

      const { result } = renderHookWithProviders(() =>
        useSummariesList({ limit: 10, offset: 0 }),
      );

      await waitFor(() => expect(result.current.isSuccess).toBe(true));
      expect(fetchSummariesMock).toHaveBeenCalledWith({ limit: 10, offset: 0 });
    });
  });

  describe("useSummaryDetail", () => {
    it("does not fetch when summaryId is 0", () => {
      renderHookWithProviders(() => useSummaryDetail(0));
      expect(fetchSummaryMock).not.toHaveBeenCalled();
    });

    it("does not fetch when summaryId is NaN", () => {
      renderHookWithProviders(() => useSummaryDetail(NaN));
      expect(fetchSummaryMock).not.toHaveBeenCalled();
    });

    it("fetches when summaryId is a positive integer", async () => {
      fetchSummaryMock.mockResolvedValueOnce({} as Awaited<ReturnType<typeof fetchSummary>>);

      const { result } = renderHookWithProviders(() => useSummaryDetail(5));

      await waitFor(() => expect(result.current.isFetching).toBe(true));
      expect(fetchSummaryMock).toHaveBeenCalledWith(5);
    });
  });

  describe("useSummaryContent", () => {
    it("does not fetch when enabled is false", () => {
      renderHookWithProviders(() => useSummaryContent(1, false));
      expect(fetchSummaryContentMock).not.toHaveBeenCalled();
    });

    it("does not fetch when summaryId is 0 even if enabled", () => {
      renderHookWithProviders(() => useSummaryContent(0, true));
      expect(fetchSummaryContentMock).not.toHaveBeenCalled();
    });
  });
});
