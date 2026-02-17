const ALLOWED_SCHEMES = new Set(["http:", "https:", "tg:"]);

export function sanitizeUrl(url: string): string {
  try {
    const parsed = new URL(url);
    return ALLOWED_SCHEMES.has(parsed.protocol) ? url : "#";
  } catch {
    return "#";
  }
}
