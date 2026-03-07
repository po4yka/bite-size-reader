import { describe, expect, it } from "vitest";
import { buildSearchQueryParams } from "./search";

describe("buildSearchQueryParams", () => {
  it("serializes power filters and array parameters", () => {
    const params = buildSearchQueryParams("climate policy", {
      limit: 50,
      offset: 20,
      mode: "hybrid",
      language: "en",
      startDate: "2026-01-01",
      endDate: "2026-02-01",
      isRead: false,
      isFavorited: true,
      minSimilarity: 0.35,
      tags: ["#energy", "#markets"],
      domains: ["ft.com", "wsj.com"],
    });

    expect(params.get("q")).toBe("climate policy");
    expect(params.get("limit")).toBe("50");
    expect(params.get("offset")).toBe("20");
    expect(params.get("mode")).toBe("hybrid");
    expect(params.get("language")).toBe("en");
    expect(params.get("start_date")).toBe("2026-01-01");
    expect(params.get("end_date")).toBe("2026-02-01");
    expect(params.get("is_read")).toBe("false");
    expect(params.get("is_favorited")).toBe("true");
    expect(params.get("min_similarity")).toBe("0.35");
    expect(params.getAll("tags")).toEqual(["#energy", "#markets"]);
    expect(params.getAll("domains")).toEqual(["ft.com", "wsj.com"]);
  });

  it("keeps base fields and omits unset optional filters", () => {
    const params = buildSearchQueryParams("ai", {});

    expect(params.get("q")).toBe("ai");
    expect(params.get("limit")).toBe("20");
    expect(params.get("offset")).toBe("0");
    expect(params.has("mode")).toBe(false);
    expect(params.has("language")).toBe(false);
    expect(params.has("start_date")).toBe(false);
    expect(params.has("end_date")).toBe(false);
    expect(params.has("is_read")).toBe(false);
    expect(params.has("is_favorited")).toBe(false);
    expect(params.has("min_similarity")).toBe(false);
  });
});
