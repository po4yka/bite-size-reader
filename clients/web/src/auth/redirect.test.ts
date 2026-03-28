import { describe, expect, it } from "vitest";
import { sanitizeRedirectPath } from "./redirect";

describe("sanitizeRedirectPath", () => {
  it("keeps safe in-app paths", () => {
    expect(sanitizeRedirectPath("/library/123")).toBe("/library/123");
    expect(sanitizeRedirectPath("/search?q=ai")).toBe("/search?q=ai");
  });

  it("falls back to library for unsafe paths", () => {
    expect(sanitizeRedirectPath(undefined)).toBe("/library");
    expect(sanitizeRedirectPath("https://evil.test")).toBe("/library");
    expect(sanitizeRedirectPath("//evil.test")).toBe("/library");
    expect(sanitizeRedirectPath("/login")).toBe("/library");
    expect(sanitizeRedirectPath("/login?from=/submit")).toBe("/library");
  });
});
