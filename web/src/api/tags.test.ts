import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiRequest } from "./client";
import { attachTags, createTag, fetchTags, mergeTags } from "./tags";

vi.mock("./client", () => ({
  apiRequest: vi.fn(),
}));

const apiRequestMock = vi.mocked(apiRequest);

describe("tags api", () => {
  beforeEach(() => {
    apiRequestMock.mockReset();
  });

  it("fetchTags maps array and fills defaults", async () => {
    apiRequestMock.mockResolvedValueOnce({
      tags: [
        { id: 1, name: "typescript" },
        { id: 2, name: "react", color: "#0af", source: "auto", summaryCount: 5, createdAt: "2026-01-01" },
      ],
    });

    const tags = await fetchTags();
    expect(tags).toHaveLength(2);
    expect(tags[0].color).toBeNull();
    expect(tags[0].source).toBe("manual");
    expect(tags[0].summaryCount).toBe(0);
    expect(tags[1].color).toBe("#0af");
    expect(tags[1].source).toBe("auto");
  });

  it("createTag sends correct body with null color when omitted", async () => {
    apiRequestMock.mockResolvedValueOnce({ id: 3, name: "rust" });

    const tag = await createTag("rust");
    expect(apiRequestMock).toHaveBeenCalledWith("/v1/tags", {
      method: "POST",
      body: JSON.stringify({ name: "rust", color: null }),
    });
    expect(tag.name).toBe("rust");
  });

  it("createTag sends color when provided", async () => {
    apiRequestMock.mockResolvedValueOnce({ id: 4, name: "go", color: "#00f" });

    await createTag("go", "#00f");
    const body = JSON.parse(apiRequestMock.mock.calls[0][1]!.body as string);
    expect(body.color).toBe("#00f");
  });

  it("mergeTags sends source_tag_ids and target_tag_id", async () => {
    apiRequestMock.mockResolvedValueOnce({ success: true });

    await mergeTags([1, 2], 3);
    expect(apiRequestMock).toHaveBeenCalledWith("/v1/tags/merge", {
      method: "POST",
      body: JSON.stringify({ source_tag_ids: [1, 2], target_tag_id: 3 }),
    });
  });

  it("attachTags sends tag_ids and tag_names", async () => {
    apiRequestMock.mockResolvedValueOnce({ success: true });

    await attachTags(10, { tagIds: [1], tagNames: ["new-tag"] });
    const body = JSON.parse(apiRequestMock.mock.calls[0][1]!.body as string);
    expect(body.tag_ids).toEqual([1]);
    expect(body.tag_names).toEqual(["new-tag"]);
  });

  it("attachTags sends null when tagIds/tagNames are omitted", async () => {
    apiRequestMock.mockResolvedValueOnce({ success: true });

    await attachTags(10, {});
    const body = JSON.parse(apiRequestMock.mock.calls[0][1]!.body as string);
    expect(body.tag_ids).toBeNull();
    expect(body.tag_names).toBeNull();
  });
});
