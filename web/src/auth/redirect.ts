const DEFAULT_REDIRECT_PATH = "/library";

export function sanitizeRedirectPath(candidate?: string | null): string {
  if (!candidate) return DEFAULT_REDIRECT_PATH;
  if (!candidate.startsWith("/")) return DEFAULT_REDIRECT_PATH;
  if (candidate.startsWith("//")) return DEFAULT_REDIRECT_PATH;
  if (candidate.startsWith("/login")) return DEFAULT_REDIRECT_PATH;
  return candidate;
}
