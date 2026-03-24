import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiRequest } from "./client";
import {
  deleteAccount,
  fetchCurrentUser,
  getWebClientId,
  listSessions,
  loginWithTelegram,
} from "./auth";

vi.mock("./client", () => ({
  apiRequest: vi.fn(),
}));

const apiRequestMock = vi.mocked(apiRequest);

describe("auth api", () => {
  beforeEach(() => {
    apiRequestMock.mockReset();
  });

  it("getWebClientId returns the web client identifier", () => {
    expect(getWebClientId()).toBe("web-carbon-v1");
  });

  it("loginWithTelegram maps tokens and always sets refreshToken to null", async () => {
    apiRequestMock.mockResolvedValueOnce({
      tokens: {
        accessToken: "tok-123",
        refreshToken: "should-be-ignored",
        expiresIn: 3600,
        tokenType: "Bearer",
      },
      sessionId: 42,
    });

    const result = await loginWithTelegram({
      id: 1,
      hash: "abc",
      auth_date: 1000,
    });

    expect(result.accessToken).toBe("tok-123");
    expect(result.refreshToken).toBeNull();
    expect(result.expiresIn).toBe(3600);
    expect(result.tokenType).toBe("Bearer");
    expect(result.sessionId).toBe(42);
  });

  it("loginWithTelegram handles missing sessionId", async () => {
    apiRequestMock.mockResolvedValueOnce({
      tokens: { accessToken: "t", expiresIn: 60, tokenType: "Bearer" },
    });

    const result = await loginWithTelegram({ id: 1, hash: "h", auth_date: 0 });
    expect(result.sessionId).toBeNull();
  });

  it("fetchCurrentUser maps fields and coerces isOwner to boolean", async () => {
    apiRequestMock.mockResolvedValueOnce({
      userId: 10,
      username: "alice",
      clientId: "web-carbon-v1",
      isOwner: 1, // truthy but not boolean
      createdAt: "2026-01-01",
    });

    const user = await fetchCurrentUser();
    expect(user.isOwner).toBe(true);
    expect(user.userId).toBe(10);
    expect(user.username).toBe("alice");
  });

  it("deleteAccount sends X-Confirm-Delete header", async () => {
    apiRequestMock.mockResolvedValueOnce({});

    await deleteAccount();
    expect(apiRequestMock).toHaveBeenCalledWith("/v1/auth/me", {
      method: "DELETE",
      headers: { "X-Confirm-Delete": "DELETE-MY-ACCOUNT" },
    });
  });

  it("listSessions extracts sessions array from envelope", async () => {
    apiRequestMock.mockResolvedValueOnce({
      sessions: [
        { id: "s1", clientId: "web", deviceInfo: null, ipAddress: null, lastUsedAt: "", createdAt: "", isCurrent: true },
      ],
    });

    const sessions = await listSessions();
    expect(sessions).toHaveLength(1);
    expect(sessions[0].id).toBe("s1");
  });
});
