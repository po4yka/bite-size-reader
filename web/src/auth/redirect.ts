const DEFAULT_REDIRECT_PATH = "/library";

const ALLOWED_PREFIXES = [
  "/library",
  "/articles",
  "/search",
  "/submit",
  "/collections",
  "/digest",
  "/digest/custom",
  "/preferences",
  "/admin",
] as const;

export function sanitizeRedirectPath(candidate?: string | null): string {
  if (!candidate) return DEFAULT_REDIRECT_PATH;
  if (!candidate.startsWith("/")) return DEFAULT_REDIRECT_PATH;
  if (candidate.startsWith("//") || candidate.startsWith("/\\")) return DEFAULT_REDIRECT_PATH;
  if (candidate.startsWith("/login")) return DEFAULT_REDIRECT_PATH;
  for (const prefix of ALLOWED_PREFIXES) {
    if (candidate === prefix || candidate.startsWith(prefix + "/") || candidate.startsWith(prefix + "?") || candidate.startsWith(prefix + "#")) {
      return candidate;
    }
  }
  return DEFAULT_REDIRECT_PATH;
}
