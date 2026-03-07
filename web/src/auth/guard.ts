import type { AuthMode, AuthStatus } from "./types";

export function canAccessProtectedRoute(mode: AuthMode, status: AuthStatus): boolean {
  if (status === "authenticated") return true;
  if (mode === "telegram-webapp" && status !== "loading") return true;
  return false;
}
