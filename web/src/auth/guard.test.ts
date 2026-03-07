import { describe, expect, it } from "vitest";
import { canAccessProtectedRoute } from "./guard";

describe("canAccessProtectedRoute", () => {
  it("allows authenticated users", () => {
    expect(canAccessProtectedRoute("jwt", "authenticated")).toBe(true);
  });

  it("blocks unauthenticated jwt users", () => {
    expect(canAccessProtectedRoute("jwt", "unauthenticated")).toBe(false);
  });

  it("blocks unauthenticated telegram webapp users", () => {
    expect(canAccessProtectedRoute("telegram-webapp", "unauthenticated")).toBe(false);
    expect(canAccessProtectedRoute("telegram-webapp", "loading")).toBe(false);
    expect(canAccessProtectedRoute("telegram-webapp", "authenticated")).toBe(true);
  });
});
