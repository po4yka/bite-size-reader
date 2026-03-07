const URL_MAX_LENGTH = 2048;
const HAS_SCHEME_RE = /^[a-z][a-z0-9+.-]*:\/\//i;

export interface SubmitUrlValidation {
  normalizedUrl: string;
  isValid: boolean;
  error: string | null;
}

function normalizeCandidate(value: string): string {
  const trimmed = value.trim();
  if (!trimmed) return "";
  if (HAS_SCHEME_RE.test(trimmed)) return trimmed;
  return `https://${trimmed}`;
}

export function validateSubmitUrl(value: string): SubmitUrlValidation {
  const normalizedCandidate = normalizeCandidate(value);
  if (!normalizedCandidate) {
    return {
      normalizedUrl: "",
      isValid: false,
      error: "URL is required.",
    };
  }

  if (normalizedCandidate.length > URL_MAX_LENGTH) {
    return {
      normalizedUrl: normalizedCandidate,
      isValid: false,
      error: "URL is too long.",
    };
  }

  let parsed: URL;
  try {
    parsed = new URL(normalizedCandidate);
  } catch {
    return {
      normalizedUrl: normalizedCandidate,
      isValid: false,
      error: "Enter a valid URL.",
    };
  }

  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
    return {
      normalizedUrl: normalizedCandidate,
      isValid: false,
      error: "Only http:// and https:// URLs are supported.",
    };
  }

  if (!parsed.hostname) {
    return {
      normalizedUrl: normalizedCandidate,
      isValid: false,
      error: "URL hostname is missing.",
    };
  }

  return {
    normalizedUrl: parsed.toString(),
    isValid: true,
    error: null,
  };
}
