import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { setStoredTokens } from "../auth/storage";
import { apiRequest } from "./client";
import { getApiSession, setApiSession } from "./session";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "Content-Type": "application/json",
    },
  });
}

describe("apiRequest", () => {
  beforeEach(() => {
    setStoredTokens(null);
    setApiSession({
      mode: "jwt",
      accessToken: null,
      refreshToken: null,
      initData: "",
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
    setStoredTokens(null);
  });

  it("extracts envelope data and normalizes mixed keys", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        success: true,
        data: {
          summary_id: 10,
          createdAt: "2026-01-01T00:00:00Z",
        },
      }),
    );

    vi.stubGlobal("fetch", fetchMock);

    const result = await apiRequest<{ summaryId: number; createdAt: string }>("/v1/test");

    expect(result).toEqual({
      summaryId: 10,
      createdAt: "2026-01-01T00:00:00Z",
    });
  });

  it("refreshes JWT tokens on 401 and retries the request", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        jsonResponse(
          {
            success: false,
            error: { message: "expired" },
          },
          401,
        ),
      )
      .mockResolvedValueOnce(
        jsonResponse({
          success: true,
          data: {
            tokens: {
              accessToken: "new-access",
              refreshToken: "new-refresh",
              expiresIn: 3600,
              tokenType: "Bearer",
            },
            sessionId: 12,
          },
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse({
          success: true,
          data: { ok: true },
        }),
      );

    vi.stubGlobal("fetch", fetchMock);

    setApiSession({
      mode: "jwt",
      accessToken: "old-access",
      refreshToken: "old-refresh",
      initData: "",
    });

    const result = await apiRequest<{ ok: boolean }>("/v1/protected");

    expect(result.ok).toBe(true);
    expect(fetchMock).toHaveBeenCalledTimes(3);

    const retryOptions = fetchMock.mock.calls[2]?.[1] as RequestInit;
    const headers = retryOptions.headers as Headers;
    expect(headers.get("Authorization")).toBe("Bearer new-access");

    const session = getApiSession();
    expect(session.accessToken).toBe("new-access");
    expect(session.refreshToken).toBe("new-refresh");
  });
});
