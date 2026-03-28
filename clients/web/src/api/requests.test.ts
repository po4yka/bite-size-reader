import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiRequest } from "./client";
import { checkDuplicate, fetchRequestStatus, retryRequest, submitUrl } from "./requests";

vi.mock("./client", () => ({
  apiRequest: vi.fn(),
}));

const apiRequestMock = vi.mocked(apiRequest);

describe("requests api client", () => {
  beforeEach(() => {
    apiRequestMock.mockReset();
  });

  it("parses queued submit responses", async () => {
    apiRequestMock.mockResolvedValueOnce({
      request: {
        requestId: 42,
        status: "pending",
        correlationId: "corr-42",
        estimatedWaitSeconds: 15,
      },
    });

    const result = await submitUrl("https://example.com/a", "en");
    expect(result).toEqual({
      kind: "queued",
      requestId: "42",
      status: "pending",
      correlationId: "corr-42",
      estimatedWaitSeconds: 15,
      createdAt: null,
    });
  });

  it("parses duplicate submit responses", async () => {
    apiRequestMock.mockResolvedValueOnce({
      isDuplicate: true,
      existingRequestId: 10,
      existingSummaryId: 99,
      message: "already summarized",
    });

    const result = await submitUrl("https://example.com/dup");
    expect(result).toEqual({
      kind: "duplicate",
      existingRequestId: "10",
      existingSummaryId: 99,
      message: "already summarized",
      summarizedAt: null,
    });
  });

  it("maps duplicate pre-check payload", async () => {
    apiRequestMock.mockResolvedValueOnce({
      isDuplicate: true,
      requestId: 21,
      summaryId: 11,
      normalizedUrl: "https://example.com/post",
      summarizedAt: "2026-01-01T00:00:00Z",
    });

    const result = await checkDuplicate("https://example.com/post");
    expect(result).toEqual({
      isDuplicate: true,
      requestId: "21",
      summaryId: 11,
      normalizedUrl: "https://example.com/post",
      summarizedAt: "2026-01-01T00:00:00Z",
    });
  });

  it("keeps completed-without-summary in processing state", async () => {
    apiRequestMock
      .mockResolvedValueOnce({
        requestId: 55,
        stage: "complete",
        status: "complete",
        progress: { percentage: 100 },
        canRetry: false,
      })
      .mockResolvedValueOnce({
        summary: null,
      });

    const status = await fetchRequestStatus("55");
    expect(status.status).toBe("processing");
    expect(status.progressPct).toBe(95);
    expect(status.summaryId).toBeNull();
  });

  it("parses retry response and returns queued request", async () => {
    apiRequestMock.mockResolvedValueOnce({
      newRequestId: 77,
      correlationId: "retry-77",
      status: "pending",
      createdAt: "2026-01-01T10:00:00Z",
    });

    const result = await retryRequest("15");
    expect(result).toEqual({
      kind: "queued",
      requestId: "77",
      status: "pending",
      correlationId: "retry-77",
      estimatedWaitSeconds: null,
      createdAt: "2026-01-01T10:00:00Z",
    });
  });
});
