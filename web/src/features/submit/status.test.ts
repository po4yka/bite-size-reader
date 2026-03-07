import { describe, expect, it } from "vitest";
import { isTerminalStatus, progressFromStatus } from "./status";

describe("submit status helpers", () => {
  it("detects terminal states", () => {
    expect(isTerminalStatus("completed")).toBe(true);
    expect(isTerminalStatus("failed")).toBe(true);
    expect(isTerminalStatus("processing")).toBe(false);
  });

  it("maps status to progress", () => {
    expect(progressFromStatus("pending", 0)).toBe(10);
    expect(progressFromStatus("crawling", 0)).toBe(40);
    expect(progressFromStatus("processing", 0)).toBe(70);
    expect(progressFromStatus("completed", 20)).toBe(100);
    expect(progressFromStatus("failed", 45)).toBe(45);
  });
});
