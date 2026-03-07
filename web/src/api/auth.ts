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
