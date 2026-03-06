import { apiRequest } from "./client";

export interface CurrentUser {
  user_id: number;
  username: string;
  client_id: string;
  is_owner: boolean;
  created_at: string;
}

interface CurrentUserBackendResponse {
  userId: number;
  username: string;
  clientId: string;
  isOwner: boolean;
  createdAt: string;
}

interface RefreshTokensBackendResponse {
  tokens: {
    accessToken: string;
    refreshToken?: string | null;
    expiresIn: number;
    tokenType: string;
  };
  sessionId?: number | null;
}

interface SessionBackendResponse {
  id: number;
  clientId?: string | null;
  deviceInfo?: string | null;
  ipAddress?: string | null;
  lastUsedAt?: string | null;
  createdAt: string;
  isCurrent?: boolean;
}

interface SessionsPayload {
  sessions: SessionBackendResponse[];
}

interface TelegramLinkStatusBackendResponse {
  linked: boolean;
  telegram_user_id?: number | null;
  username?: string | null;
  photo_url?: string | null;
  first_name?: string | null;
  last_name?: string | null;
  linked_at?: string | null;
  link_nonce_expires_at?: string | null;
  link_nonce?: string | null;
}

interface TelegramLinkBeginBackendResponse {
  nonce: string;
  expires_at: string;
}

export interface SessionInfo {
  id: number;
  client_id: string | null;
  device_info: string | null;
  ip_address: string | null;
  last_used_at: string | null;
  created_at: string;
  is_current: boolean;
}

export interface AuthTokens {
  access_token: string;
  refresh_token: string | null;
  expires_in: number;
  token_type: string;
  session_id: number | null;
}

export interface TelegramLinkStatus {
  linked: boolean;
  telegram_user_id: number | null;
  username: string | null;
  photo_url: string | null;
  first_name: string | null;
  last_name: string | null;
  linked_at: string | null;
  link_nonce_expires_at: string | null;
  link_nonce: string | null;
}

export function fetchCurrentUser(): Promise<CurrentUser> {
  return apiRequest<CurrentUserBackendResponse>("/v1/auth/me").then((payload) => ({
    user_id: payload.userId,
    username: payload.username,
    client_id: payload.clientId,
    is_owner: payload.isOwner,
    created_at: payload.createdAt,
  }));
}

export function refreshAccessToken(refreshToken: string): Promise<AuthTokens> {
  return apiRequest<RefreshTokensBackendResponse>("/v1/auth/refresh", {
    method: "POST",
    body: JSON.stringify({ refresh_token: refreshToken }),
  }).then((payload) => ({
    access_token: payload.tokens.accessToken,
    refresh_token: payload.tokens.refreshToken ?? null,
    expires_in: payload.tokens.expiresIn,
    token_type: payload.tokens.tokenType,
    session_id: payload.sessionId ?? null,
  }));
}

export function logout(refreshToken: string): Promise<{ message: string }> {
  return apiRequest<{ message?: string }>("/v1/auth/logout", {
    method: "POST",
    body: JSON.stringify({ refresh_token: refreshToken }),
  }).then((payload) => ({
    message: payload.message ?? "Logged out successfully",
  }));
}

export function fetchSessions(): Promise<{ sessions: SessionInfo[] }> {
  return apiRequest<SessionsPayload>("/v1/auth/sessions").then((payload) => ({
    sessions: payload.sessions.map((session) => ({
      id: session.id,
      client_id: session.clientId ?? null,
      device_info: session.deviceInfo ?? null,
      ip_address: session.ipAddress ?? null,
      last_used_at: session.lastUsedAt ?? null,
      created_at: session.createdAt,
      is_current: Boolean(session.isCurrent),
    })),
  }));
}

export function fetchTelegramLinkStatus(): Promise<TelegramLinkStatus> {
  return apiRequest<TelegramLinkStatusBackendResponse>("/v1/auth/me/telegram").then((payload) => ({
    linked: payload.linked,
    telegram_user_id: payload.telegram_user_id ?? null,
    username: payload.username ?? null,
    photo_url: payload.photo_url ?? null,
    first_name: payload.first_name ?? null,
    last_name: payload.last_name ?? null,
    linked_at: payload.linked_at ?? null,
    link_nonce_expires_at: payload.link_nonce_expires_at ?? null,
    link_nonce: payload.link_nonce ?? null,
  }));
}

export function beginTelegramLink(): Promise<{ nonce: string; expires_at: string }> {
  return apiRequest<TelegramLinkBeginBackendResponse>("/v1/auth/me/telegram/link", {
    method: "POST",
  });
}

export function completeTelegramLink(payload: {
  nonce: string;
  id: number;
  hash: string;
  auth_date: number;
  username?: string;
  first_name?: string;
  last_name?: string;
  photo_url?: string;
  client_id?: string;
}): Promise<TelegramLinkStatus> {
  return apiRequest<TelegramLinkStatusBackendResponse>("/v1/auth/me/telegram/complete", {
    method: "POST",
    body: JSON.stringify(payload),
  }).then((status) => ({
    linked: status.linked,
    telegram_user_id: status.telegram_user_id ?? null,
    username: status.username ?? null,
    photo_url: status.photo_url ?? null,
    first_name: status.first_name ?? null,
    last_name: status.last_name ?? null,
    linked_at: status.linked_at ?? null,
    link_nonce_expires_at: status.link_nonce_expires_at ?? null,
    link_nonce: status.link_nonce ?? null,
  }));
}

export function unlinkTelegram(): Promise<TelegramLinkStatus> {
  return apiRequest<TelegramLinkStatusBackendResponse>("/v1/auth/me/telegram", {
    method: "DELETE",
  }).then((payload) => ({
    linked: payload.linked,
    telegram_user_id: payload.telegram_user_id ?? null,
    username: payload.username ?? null,
    photo_url: payload.photo_url ?? null,
    first_name: payload.first_name ?? null,
    last_name: payload.last_name ?? null,
    linked_at: payload.linked_at ?? null,
    link_nonce_expires_at: payload.link_nonce_expires_at ?? null,
    link_nonce: payload.link_nonce ?? null,
  }));
}
