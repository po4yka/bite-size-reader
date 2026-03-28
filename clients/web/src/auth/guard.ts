import type { AuthMode, AuthStatus } from "./types";

export function canAccessProtectedRoute(mode: AuthMode, status: AuthStatus): boolean {
  void mode;
  return status === "authenticated";
}
