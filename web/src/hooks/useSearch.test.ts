import { describe, expect, it, vi, beforeEach } from "vitest";
import { renderHookWithProviders } from "../testing/render";
import { useSearchResults } from "./useSearch";

vi.mock("../api/search", () => ({
  searchSummaries: vi.fn(),
  fetchTrendingTopics: vi.fn(),
}));

const { searchSummaries } = await import("../api/search");
const searchMock = vi.mocked(searchSummaries);

describe("useSearch hooks", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("does not fetch when query is empty", () => {
    renderHookWithProviders(() => useSearchResults(""));
    expect(searchMock).not.toHaveBeenCalled();
  });

  it("does not fetch when query is a single character", () => {
    renderHookWithProviders(() => useSearchResults("a"));
    expect(searchMock).not.toHaveBeenCalled();
  });

  it("does not fetch when enabled is false", () => {
    renderHookWithProviders(() => useSearchResults("test query", {}, false));
    expect(searchMock).not.toHaveBeenCalled();
  });

  it("fetches when query has 2+ characters", () => {
    searchMock.mockResolvedValueOnce({} as Awaited<ReturnType<typeof searchSummaries>>);
    renderHookWithProviders(() => useSearchResults("ab"));
    expect(searchMock).toHaveBeenCalledWith("ab", {});
  });
});
