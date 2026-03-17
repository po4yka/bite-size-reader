import { apiRequest } from "./client";
import type { AuthTokens } from "../auth/types";

interface SocialLoginData {
  tokens: AuthTokens;
  sessionId?: number | null;
}

export async function loginWithApple(
  idToken: string,
  clientId: string,
  authCode?: string,
  givenName?: string,
  familyName?: string,
): Promise<AuthTokens> {
  const result = await apiRequest<SocialLoginData>("/v1/auth/apple-login", {
    method: "POST",
    body: JSON.stringify({
      id_token: idToken,
      client_id: clientId,
      ...(authCode !== undefined && { authorization_code: authCode }),
      ...(givenName !== undefined && { given_name: givenName }),
      ...(familyName !== undefined && { family_name: familyName }),
    }),
  });

  return {
    accessToken: result.tokens.accessToken,
    refreshToken: result.tokens.refreshToken ?? null,
    expiresIn: result.tokens.expiresIn,
    tokenType: result.tokens.tokenType,
    sessionId: result.tokens.sessionId ?? null,
  };
}

export async function loginWithGoogle(idToken: string, clientId: string): Promise<AuthTokens> {
  const result = await apiRequest<SocialLoginData>("/v1/auth/google-login", {
    method: "POST",
    body: JSON.stringify({
      id_token: idToken,
      client_id: clientId,
    }),
  });

  return {
    accessToken: result.tokens.accessToken,
    refreshToken: result.tokens.refreshToken ?? null,
    expiresIn: result.tokens.expiresIn,
    tokenType: result.tokens.tokenType,
    sessionId: result.tokens.sessionId ?? null,
  };
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
    refreshToken: result.tokens.refreshToken ?? null,
    expiresIn: result.tokens.expiresIn,
    tokenType: result.tokens.tokenType,
    sessionId: result.tokens.sessionId ?? null,
  };
}
