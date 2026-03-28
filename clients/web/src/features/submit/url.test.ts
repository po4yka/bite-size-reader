import { describe, expect, it } from "vitest";
import { validateSubmitUrl } from "./url";

describe("validateSubmitUrl", () => {
  it("accepts valid https URLs", () => {
    const result = validateSubmitUrl("https://example.com/article");
    expect(result.isValid).toBe(true);
    expect(result.error).toBeNull();
    expect(result.normalizedUrl).toBe("https://example.com/article");
  });

  it("adds https scheme when missing", () => {
    const result = validateSubmitUrl("example.com/path");
    expect(result.isValid).toBe(true);
    expect(result.normalizedUrl).toBe("https://example.com/path");
  });

  it("rejects unsupported schemes", () => {
    const result = validateSubmitUrl("ftp://example.com/file");
    expect(result.isValid).toBe(false);
    expect(result.error).toContain("http://");
  });

  it("rejects invalid URL input", () => {
    const result = validateSubmitUrl("not a real url");
    expect(result.isValid).toBe(false);
    expect(result.error).toBeTruthy();
  });
});
