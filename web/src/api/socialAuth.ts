import { apiRequest } from "./client";
import type { AuthTokens } from "../auth/types";

interface SocialLoginData {
  tokens: AuthTokens;
  sessionId?: number | null;
}

export async function loginWithSecret(secretKey: string, clientId: string): Promise<AuthTokens> {
  const result = await apiRequest<SocialLoginData>("/v1/auth/secret-login", {
    method: "POST",
    body: JSON.stringify({
      secret_key: secretKey,
      client_id: clientId,
    }),
  });

  return {
    accessToken: result.tokens.accessToken,
    refreshToken: null, // httpOnly cookie handles refresh token
    expiresIn: result.tokens.expiresIn,
    tokenType: result.tokens.tokenType,
    sessionId: result.tokens.sessionId ?? null,
  };
}
