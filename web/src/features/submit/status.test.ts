import { describe, expect, it } from "vitest";
import { formatEta, isTerminalStatus, progressFromStatus, statusLabel } from "./status";

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

  it("formats status labels and ETA", () => {
    expect(statusLabel("pending")).toBe("Waiting in queue");
    expect(statusLabel("crawling")).toBe("Extracting content");
    expect(statusLabel("processing")).toBe("Generating summary");
    expect(statusLabel("completed")).toBe("Completed");
    expect(statusLabel("failed")).toBe("Failed");

    expect(formatEta(null)).toBeNull();
    expect(formatEta(0)).toBeNull();
    expect(formatEta(45)).toBe("~45s remaining");
    expect(formatEta(61)).toBe("~2m remaining");
  });
});
