import { apiRequest } from "./client";
import type { AuthTokens, AuthUser, TelegramAuthPayload } from "../auth/types";

const WEB_CLIENT_ID = "web-carbon-v1";

interface TelegramLoginData {
  tokens: {
    accessToken: string;
    refreshToken?: string | null;
    expiresIn: number;
    tokenType: string;
  };
  sessionId?: number | null;
}

export function getWebClientId(): string {
  return WEB_CLIENT_ID;
}

export async function loginWithTelegram(payload: TelegramAuthPayload): Promise<AuthTokens> {
  const result = await apiRequest<TelegramLoginData>("/v1/auth/telegram-login", {
    method: "POST",
    body: JSON.stringify({
      ...payload,
      client_id: WEB_CLIENT_ID,
    }),
  });

  return {
    accessToken: result.tokens.accessToken,
    refreshToken: result.tokens.refreshToken ?? null,
    expiresIn: result.tokens.expiresIn,
    tokenType: result.tokens.tokenType,
    sessionId: result.sessionId ?? null,
  };
}

interface CurrentUserData {
  userId: number;
  username: string;
  clientId: string;
  isOwner: boolean;
  createdAt: string;
}

export async function fetchCurrentUser(): Promise<AuthUser> {
  const user = await apiRequest<CurrentUserData>("/v1/auth/me");
  return {
    userId: user.userId,
    username: user.username,
    clientId: user.clientId,
    isOwner: Boolean(user.isOwner),
    createdAt: user.createdAt,
  };
}

export async function deleteAccount(): Promise<void> {
  await apiRequest<Record<string, never>>("/v1/auth/me", {
    method: "DELETE",
  });
}

export interface AuthSession {
  id: string;
  clientId: string;
  deviceInfo: string | null;
  ipAddress: string | null;
  lastUsedAt: string;
  createdAt: string;
  isCurrent: boolean;
}

interface SessionsResponse {
  sessions: AuthSession[];
}

export async function listSessions(): Promise<AuthSession[]> {
  const result = await apiRequest<SessionsResponse>("/v1/auth/sessions");
  return result.sessions;
}

// TODO: backend endpoint DELETE /v1/auth/sessions/{session_id} is not yet implemented
export async function deleteSession(sessionId: string): Promise<void> {
  await apiRequest<Record<string, never>>(`/v1/auth/sessions/${sessionId}`, {
    method: "DELETE",
  });
}

export interface TelegramLinkStatus {
  linked: boolean;
  telegramUsername?: string;
  linkedAt?: string;
}

export async function getTelegramLinkStatus(): Promise<TelegramLinkStatus> {
  return apiRequest<TelegramLinkStatus>("/v1/auth/me/telegram");
}

export async function beginTelegramLink(): Promise<{ nonce: string; expiresIn: number }> {
  return apiRequest<{ nonce: string; expiresIn: number }>("/v1/auth/me/telegram/link", {
    method: "POST",
  });
}

export interface TelegramAuthForLink {
  telegramUserId: number;
  authHash: string;
  authDate: number;
  username?: string;
  firstName?: string;
  lastName?: string;
}

export async function completeTelegramLink(
  nonce: string,
  telegramAuth: TelegramAuthForLink,
): Promise<TelegramLinkStatus> {
  return apiRequest<TelegramLinkStatus>("/v1/auth/me/telegram/complete", {
    method: "POST",
    body: JSON.stringify({
      nonce,
      telegram_user_id: telegramAuth.telegramUserId,
      auth_hash: telegramAuth.authHash,
      auth_date: telegramAuth.authDate,
      username: telegramAuth.username,
      first_name: telegramAuth.firstName,
      last_name: telegramAuth.lastName,
    }),
  });
}

export async function unlinkTelegram(): Promise<void> {
  await apiRequest<Record<string, never>>("/v1/auth/me/telegram", {
    method: "DELETE",
  });
}
