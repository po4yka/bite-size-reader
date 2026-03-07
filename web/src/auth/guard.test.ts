import { describe, expect, it } from "vitest";
import { canAccessProtectedRoute } from "./guard";

describe("canAccessProtectedRoute", () => {
  it("allows authenticated users", () => {
    expect(canAccessProtectedRoute("jwt", "authenticated")).toBe(true);
  });

  it("blocks unauthenticated jwt users", () => {
    expect(canAccessProtectedRoute("jwt", "unauthenticated")).toBe(false);
  });

  it("allows telegram webapp users unless loading", () => {
    expect(canAccessProtectedRoute("telegram-webapp", "unauthenticated")).toBe(true);
    expect(canAccessProtectedRoute("telegram-webapp", "loading")).toBe(false);
  });
});
