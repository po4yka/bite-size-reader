import { describe, it, expect, vi, beforeEach } from "vitest";
import { apiRequest } from "./client";

function mockFetch(status: number, body: unknown): void {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: status >= 200 && status < 300,
      status,
      json: vi.fn().mockResolvedValue(body),
    }),
  );
}

beforeEach(() => {
  vi.unstubAllGlobals();
});

describe("apiRequest", () => {
  it("returns data on a successful response", async () => {
    mockFetch(200, { success: true, data: { id: 1 } });

    const result = await apiRequest<{ id: number }>("/api/test");

    expect(result).toEqual({ id: 1 });
  });

  it("throws on a failed response", async () => {
    mockFetch(200, { success: false, data: null });
    // Simulate a non-ok response (404)
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 404,
        json: vi.fn().mockResolvedValue({ error: { message: "Not found" } }),
      }),
    );

    await expect(apiRequest("/api/missing")).rejects.toThrow("Not found.");
  });

  it("throws a generic error for unknown status codes", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
        json: vi.fn().mockResolvedValue({}),
      }),
    );

    await expect(apiRequest("/api/error")).rejects.toThrow("Request failed (500)");
  });

  it("sets X-Telegram-Init-Data header when Telegram WebApp initData is available", async () => {
    const initData = "query_id=abc&user=123";
    vi.stubGlobal("Telegram", { WebApp: { initData } });
    mockFetch(200, { data: null });

    const fetchMock = vi.mocked(fetch);
    await apiRequest("/api/test").catch(() => {});

    const callArgs = fetchMock.mock.calls[0];
    const headers = callArgs[1]?.headers as Record<string, string>;
    expect(headers["X-Telegram-Init-Data"]).toBe(initData);
  });
});
