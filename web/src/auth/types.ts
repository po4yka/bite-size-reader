export type AuthMode = "telegram-webapp" | "jwt";
export type AuthStatus = "loading" | "authenticated" | "unauthenticated";

export interface AuthTokens {
  accessToken: string;
  refreshToken: string | null;
  expiresIn: number;
  tokenType: string;
  sessionId: number | null;
}

export interface AuthUser {
  userId: number;
  username: string;
  clientId: string;
  isOwner: boolean;
  createdAt: string;
}

export interface TelegramAuthPayload {
  id: number;
  hash: string;
  auth_date: number;
  username?: string;
  first_name?: string;
  last_name?: string;
  photo_url?: string;
}

export interface AppleAuthPayload {
  idToken: string;
  clientId: string;
  authCode?: string;
  givenName?: string;
  familyName?: string;
}

export interface GoogleAuthPayload {
  idToken: string;
  clientId: string;
}

export interface SecretAuthPayload {
  secretKey: string;
  clientId: string;
}
