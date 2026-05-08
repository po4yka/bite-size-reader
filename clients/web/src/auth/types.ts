export type AuthMode = "telegram-webapp" | "jwt";
export type AuthStatus = "loading" | "authenticated" | "unauthenticated";

export interface AuthTokens {
  accessToken: string;
  refreshToken: string | null;
  expiresIn: number;
  tokenType: string;
  sessionId: number | null;
  // True when the user picked Remember Me (or for legacy Telegram/secret-key
  // logins that always persist). False for credentials-login with the box
  // unchecked: tokens go to sessionStorage so they vanish on browser close.
  // The storage layer reads this on refresh to write back to the same bucket.
  persistent?: boolean;
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

export interface SecretAuthPayload {
  secretKey: string;
  clientId: string;
}

export interface CredentialsAuthPayload {
  identifier: string; // nickname or email; "@" presence routes to email branch
  password: string;
  rememberMe: boolean;
  clientId: string;
}
