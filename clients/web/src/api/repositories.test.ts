import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiRequest } from "./client";
import {
  fetchRepositories,
  fetchRepository,
  ingestRepository,
  searchRepositories,
} from "./repositories";

vi.mock("./client", () => ({
  apiRequest: vi.fn(),
}));

const apiRequestMock = vi.mocked(apiRequest);

describe("repositories api", () => {
  beforeEach(() => {
    apiRequestMock.mockReset();
  });

  describe("fetchRepositories", () => {
    it("calls the correct endpoint with no params", async () => {
      apiRequestMock.mockResolvedValueOnce({
        repositories: [],
        pagination: { total: 0, limit: 20, offset: 0, hasMore: false },
      });

      await fetchRepositories();

      expect(apiRequestMock).toHaveBeenCalledOnce();
      expect(apiRequestMock.mock.calls[0][0]).toMatch(/^\/v1\/repositories\?/);
    });

    it("serialises all filter params into the query string", async () => {
      apiRequestMock.mockResolvedValueOnce({
        repositories: [],
        pagination: { total: 0, limit: 10, offset: 5, hasMore: false },
      });

      await fetchRepositories({
        is_starred: true,
        language: "TypeScript",
        topic: "react",
        source: "manual",
        pending_analysis: false,
        sort: "stars_desc",
        limit: 10,
        offset: 5,
      });

      const url = apiRequestMock.mock.calls[0][0] as string;
      expect(url).toContain("is_starred=true");
      expect(url).toContain("language=TypeScript");
      expect(url).toContain("topic=react");
      expect(url).toContain("source=manual");
      expect(url).toContain("pending_analysis=false");
      expect(url).toContain("sort=stars_desc");
      expect(url).toContain("limit=10");
      expect(url).toContain("offset=5");
    });

    it("returns the response from the server unchanged", async () => {
      const payload = {
        repositories: [
          {
            id: 1,
            github_id: 100,
            full_name: "owner/repo",
            owner: "owner",
            name: "repo",
            description: null,
            primary_language: "TypeScript",
            topics: ["react"],
            stars: 42,
            forks: 3,
            is_starred: true,
            is_archived: false,
            pushed_at: "2024-01-01T00:00:00Z",
            last_synced_at: "2024-01-02T00:00:00Z",
            pending_analysis: false,
            has_analysis: true,
            source: "manual",
          },
        ],
        pagination: { total: 1, limit: 20, offset: 0, hasMore: false },
      };
      apiRequestMock.mockResolvedValueOnce(payload);

      const result = await fetchRepositories();
      expect(result.repositories).toHaveLength(1);
      expect(result.repositories[0].full_name).toBe("owner/repo");
      expect(result.pagination.total).toBe(1);
    });
  });

  describe("fetchRepository", () => {
    it("calls the correct endpoint for a given id", async () => {
      apiRequestMock.mockResolvedValueOnce({});

      await fetchRepository(99);

      expect(apiRequestMock.mock.calls[0][0]).toBe("/v1/repositories/99");
    });
  });

  describe("ingestRepository", () => {
    it("posts the url in the request body", async () => {
      apiRequestMock.mockResolvedValueOnce({
        repository_id: 7,
        status: "pending",
        full_name: "owner/new-repo",
      });

      const result = await ingestRepository("https://github.com/owner/new-repo");

      expect(apiRequestMock.mock.calls[0][0]).toBe("/v1/repositories");
      const opts = apiRequestMock.mock.calls[0][1] as RequestInit;
      expect(opts.method).toBe("POST");
      expect(JSON.parse(opts.body as string)).toEqual({ url: "https://github.com/owner/new-repo" });
      expect(result.status).toBe("pending");
    });
  });

  describe("searchRepositories", () => {
    it("includes q param and optional filters", async () => {
      apiRequestMock.mockResolvedValueOnce({
        results: [],
        pagination: { total: 0, limit: 10, offset: 0, hasMore: false },
        query: "react hooks",
      });

      await searchRepositories({
        q: "react hooks",
        limit: 10,
        languages: ["TypeScript", "JavaScript"],
        topics: ["react"],
        is_starred: true,
      });

      const url = apiRequestMock.mock.calls[0][0] as string;
      expect(url).toContain("/v1/search/repositories");
      expect(url).toContain("q=react+hooks");
      expect(url).toContain("limit=10");
      expect(url).toContain("is_starred=true");
      // Multi-value params appended separately
      const params = new URLSearchParams(url.split("?")[1]);
      expect(params.getAll("languages")).toEqual(["TypeScript", "JavaScript"]);
      expect(params.getAll("topics")).toEqual(["react"]);
    });
  });
});
