import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiRequest } from "./client";
import {
  fetchSummaries,
  fetchSummary,
  fetchSummaryContent,
  getSummaryAudioUrl,
  toggleSummaryFavorite,
} from "./summaries";

vi.mock("./client", () => ({
  apiRequest: vi.fn(),
}));

const apiRequestMock = vi.mocked(apiRequest);

describe("summaries api", () => {
  beforeEach(() => {
    apiRequestMock.mockReset();
  });

  describe("fetchSummaries", () => {
    it("builds query params from filter options", async () => {
      apiRequestMock.mockResolvedValueOnce({
        summaries: [],
        pagination: { total: 0, limit: 10, offset: 0, hasMore: false },
      });

      await fetchSummaries({ limit: 10, offset: 5, isRead: false, sort: "created_at_desc" });

      const url = apiRequestMock.mock.calls[0][0];
      expect(url).toContain("limit=10");
      expect(url).toContain("offset=5");
      expect(url).toContain("is_read=false");
      expect(url).toContain("sort=created_at_desc");
    });

    it("maps summaries through mapSummaryCompact with defaults", async () => {
      apiRequestMock.mockResolvedValueOnce({
        summaries: [{ id: 1 }], // minimal payload — all other fields should get defaults
        pagination: { total: 1, limit: 20, offset: 0, hasMore: false },
      });

      const result = await fetchSummaries();
      expect(result.summaries).toHaveLength(1);
      expect(result.summaries[0].title).toBe("Untitled");
      expect(result.summaries[0].topicTags).toEqual([]);
      expect(result.summaries[0].readingTimeMin).toBe(0);
    });
  });

  describe("fetchSummary", () => {
    it("maps nested payload to flat SummaryDetail", async () => {
      apiRequestMock.mockResolvedValueOnce({
        summary: {
          summary250: "short",
          summary1000: "long",
          tldr: "tldr",
          keyIdeas: ["idea1"],
          topicTags: ["tag1"],
          entities: {
            people: ["Alice"],
            organizations: ["Acme"],
          },
          estimatedReadingTimeMin: 5,
          keyStats: [{ label: "Users", value: 100, unit: "k" }],
        },
        request: { id: "req-1", url: "https://example.com" },
        source: { title: "Test Article", domain: "example.com", url: "https://example.com" },
        processing: { confidence: 0.85, hallucinationRisk: "low" },
      });

      const detail = await fetchSummary(42);
      expect(detail.id).toBe(42);
      expect(detail.title).toBe("Test Article");
      expect(detail.summary250).toBe("short");
      expect(detail.entities).toEqual([
        { name: "Alice", type: "person" },
        { name: "Acme", type: "organization" },
      ]);
      expect(detail.confidence).toBe(0.85);
      expect(detail.keyStats[0].value).toBe("100 k");
    });

    it("fills defaults when summary fields are missing", async () => {
      apiRequestMock.mockResolvedValueOnce({
        summary: {},
        request: {},
        source: {},
        processing: {},
      });

      const detail = await fetchSummary(1);
      expect(detail.title).toBe("Untitled");
      expect(detail.keyIdeas).toEqual([]);
      expect(detail.hallucinationRisk).toBe("unknown");
    });
  });

  describe("fetchSummaryContent", () => {
    it("extracts nested content and format", async () => {
      apiRequestMock.mockResolvedValueOnce({
        content: { content: "# Hello", format: "markdown" },
      });

      const result = await fetchSummaryContent(1);
      expect(result.content).toBe("# Hello");
      expect(result.format).toBe("markdown");
    });
  });

  describe("toggleSummaryFavorite", () => {
    it("coerces isFavorited to boolean", async () => {
      apiRequestMock.mockResolvedValueOnce({ isFavorited: 1 });

      const result = await toggleSummaryFavorite(5);
      expect(result.isFavorited).toBe(true);
    });
  });

  describe("getSummaryAudioUrl", () => {
    it("throws for invalid summaryId", () => {
      expect(() => getSummaryAudioUrl(0)).toThrow();
      expect(() => getSummaryAudioUrl(-1)).toThrow();
      expect(() => getSummaryAudioUrl(NaN)).toThrow();
    });
  });
});
