import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiRequest } from "./client";
import {
  connectGithubPat,
  disconnectGithub,
  getGithubStatus,
  pollDeviceFlow,
  startDeviceFlow,
} from "./github";

vi.mock("./client", () => ({
  apiRequest: vi.fn(),
}));

const apiRequestMock = vi.mocked(apiRequest);

describe("github api", () => {
  beforeEach(() => {
    apiRequestMock.mockReset();
  });

  describe("getGithubStatus", () => {
    it("calls GET /v1/auth/github/status and returns the response", async () => {
      const payload = {
        is_connected: true,
        auth_method: "pat",
        github_login: "octocat",
        github_user_id: 1,
        status: "active",
        last_synced_at: "2024-01-01T00:00:00Z",
        repo_count: 12,
      };
      apiRequestMock.mockResolvedValueOnce(payload);

      const result = await getGithubStatus();

      expect(apiRequestMock.mock.calls[0][0]).toBe("/v1/auth/github/status");
      expect(result.github_login).toBe("octocat");
      expect(result.is_connected).toBe(true);
    });
  });

  describe("connectGithubPat", () => {
    it("posts the token in the request body to /v1/auth/github/pat", async () => {
      apiRequestMock.mockResolvedValueOnce({
        login: "octocat",
        github_user_id: 1,
        auth_method: "pat",
        status: "active",
      });

      const result = await connectGithubPat("ghp_abc123");

      expect(apiRequestMock.mock.calls[0][0]).toBe("/v1/auth/github/pat");
      const opts = apiRequestMock.mock.calls[0][1] as RequestInit;
      expect(opts.method).toBe("POST");
      expect(JSON.parse(opts.body as string)).toEqual({ token: "ghp_abc123" });
      expect(result.login).toBe("octocat");
    });
  });

  describe("disconnectGithub", () => {
    it("sends DELETE to /v1/auth/github", async () => {
      apiRequestMock.mockResolvedValueOnce(undefined);

      await disconnectGithub();

      expect(apiRequestMock.mock.calls[0][0]).toBe("/v1/auth/github");
      const opts = apiRequestMock.mock.calls[0][1] as RequestInit;
      expect(opts.method).toBe("DELETE");
    });
  });

  describe("startDeviceFlow", () => {
    it("posts to /v1/auth/github/device/start and returns device flow data", async () => {
      const payload = {
        user_code: "ABCD-1234",
        verification_uri: "https://github.com/login/device",
        device_code: "device_xyz",
        interval: 5,
        expires_in: 900,
      };
      apiRequestMock.mockResolvedValueOnce(payload);

      const result = await startDeviceFlow();

      expect(apiRequestMock.mock.calls[0][0]).toBe("/v1/auth/github/device/start");
      const opts = apiRequestMock.mock.calls[0][1] as RequestInit;
      expect(opts.method).toBe("POST");
      expect(result.user_code).toBe("ABCD-1234");
      expect(result.interval).toBe(5);
    });
  });

  describe("pollDeviceFlow", () => {
    it("posts device_code in body to /v1/auth/github/device/poll", async () => {
      apiRequestMock.mockResolvedValueOnce({ status: "pending" });

      const result = await pollDeviceFlow("device_xyz");

      expect(apiRequestMock.mock.calls[0][0]).toBe("/v1/auth/github/device/poll");
      const opts = apiRequestMock.mock.calls[0][1] as RequestInit;
      expect(opts.method).toBe("POST");
      expect(JSON.parse(opts.body as string)).toEqual({ device_code: "device_xyz" });
      expect(result.status).toBe("pending");
    });

    it("returns ok status with login on success", async () => {
      apiRequestMock.mockResolvedValueOnce({
        status: "ok",
        login: "octocat",
        github_user_id: 1,
        auth_method: "oauth_device",
        integration_status: "active",
      });

      const result = await pollDeviceFlow("device_xyz");

      expect(result.status).toBe("ok");
      expect(result.login).toBe("octocat");
    });
  });
});
