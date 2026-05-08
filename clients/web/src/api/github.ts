import { apiRequest } from "./client";

export interface GitHubStatusResponse {
  is_connected: boolean;
  auth_method: "pat" | "oauth_device" | null;
  github_login: string | null;
  github_user_id: number | null;
  status: "active" | "needs_reauth" | "revoked" | null;
  last_synced_at: string | null;
  repo_count: number;
}

export interface PATSubmitResponse {
  login: string;
  github_user_id: number;
  auth_method: string;
  status: string;
}

export interface DeviceFlowStartResponse {
  user_code: string;
  verification_uri: string;
  device_code: string;
  interval: number;
  expires_in: number;
}

export type DeviceFlowPollStatus = "pending" | "slow_down" | "expired" | "ok" | "denied";

export interface DeviceFlowPollResponse {
  status: DeviceFlowPollStatus;
  login?: string | null;
  github_user_id?: number | null;
  auth_method?: string | null;
  integration_status?: string | null;
}

export async function getGithubStatus(): Promise<GitHubStatusResponse> {
  return apiRequest<GitHubStatusResponse>("/v1/auth/github/status");
}

export async function connectGithubPat(token: string): Promise<PATSubmitResponse> {
  return apiRequest<PATSubmitResponse>("/v1/auth/github/pat", {
    method: "POST",
    body: JSON.stringify({ token }),
  });
}

export async function disconnectGithub(): Promise<void> {
  await apiRequest<void>("/v1/auth/github", { method: "DELETE" });
}

export async function startDeviceFlow(): Promise<DeviceFlowStartResponse> {
  return apiRequest<DeviceFlowStartResponse>("/v1/auth/github/device/start", { method: "POST" });
}

export async function pollDeviceFlow(deviceCode: string): Promise<DeviceFlowPollResponse> {
  return apiRequest<DeviceFlowPollResponse>("/v1/auth/github/device/poll", {
    method: "POST",
    body: JSON.stringify({ device_code: deviceCode }),
  });
}
