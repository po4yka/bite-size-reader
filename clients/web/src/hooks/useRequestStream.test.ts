import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useRequestStream } from "./useRequestStream";
import type { components } from "../api/generated";

type StreamPhaseEvent = components["schemas"]["StreamPhaseEvent"];
type StreamSectionEvent = components["schemas"]["StreamSectionEvent"];
type StreamDoneEvent = components["schemas"]["StreamDoneEvent"];

// ---------------------------------------------------------------------------
// Mock the streamRequest module
// ---------------------------------------------------------------------------

vi.mock("../api/streamRequest", () => ({
  subscribeToRequest: vi.fn(),
}));

const { subscribeToRequest } = await import("../api/streamRequest");
const subscribeMock = vi.mocked(subscribeToRequest);

// ---------------------------------------------------------------------------
// Test helpers
// ---------------------------------------------------------------------------

type Handlers = Parameters<typeof subscribeToRequest>[1];

/** Capture handlers from the latest subscribeToRequest call. */
function captureHandlers(): Handlers {
  const calls = subscribeMock.mock.calls;
  if (calls.length === 0) throw new Error("subscribeToRequest was not called");
  return calls[calls.length - 1][1];
}

beforeEach(() => {
  vi.clearAllMocks();
  // Default: return a no-op cancel function.
  subscribeMock.mockReturnValue(() => {});
});

afterEach(() => {
  vi.clearAllMocks();
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("useRequestStream", () => {
  it("starts with phase=null, isStreaming=true, fellBack=false", () => {
    subscribeMock.mockReturnValue(() => {});

    const { result } = renderHook(() => useRequestStream(1));

    expect(result.current.phase).toBeNull();
    expect(result.current.isStreaming).toBe(true);
    expect(result.current.fellBack).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it("does not subscribe when requestId is null", () => {
    renderHook(() => useRequestStream(null));
    expect(subscribeMock).not.toHaveBeenCalled();
  });

  it("updates phase after onPhase events", async () => {
    const { result } = renderHook(() => useRequestStream(42));
    const handlers = captureHandlers();

    await act(async () => {
      handlers.onPhase?.({
        kind: "phase",
        payload: { phase: "extracting" },
        timestamp: new Date().toISOString(),
        correlation_id: "c1",
      } as StreamPhaseEvent);
    });

    expect(result.current.phase).toBe("extracting");

    await act(async () => {
      handlers.onPhase?.({
        kind: "phase",
        payload: { phase: "summarizing" },
        timestamp: new Date().toISOString(),
        correlation_id: "c1",
      } as StreamPhaseEvent);
    });

    expect(result.current.phase).toBe("summarizing");
  });

  it("populates sectionsBySlug after onSection events", async () => {
    const { result } = renderHook(() => useRequestStream("req-123"));
    const handlers = captureHandlers();

    await act(async () => {
      handlers.onSection?.({
        kind: "section",
        payload: { section: "tldr", content: "Quick summary", partial: false },
        timestamp: new Date().toISOString(),
        correlation_id: "c1",
      } as StreamSectionEvent);
    });

    expect(result.current.sectionsBySlug["tldr"]).toBe("Quick summary");

    await act(async () => {
      handlers.onSection?.({
        kind: "section",
        payload: { section: "summary_250", content: "Longer text", partial: false },
        timestamp: new Date().toISOString(),
        correlation_id: "c1",
      } as StreamSectionEvent);
    });

    expect(result.current.sectionsBySlug["summary_250"]).toBe("Longer text");
    // tldr must still be present.
    expect(result.current.sectionsBySlug["tldr"]).toBe("Quick summary");
  });

  it("sets isStreaming=false after onDone", async () => {
    const { result } = renderHook(() => useRequestStream(7));
    const handlers = captureHandlers();

    expect(result.current.isStreaming).toBe(true);

    await act(async () => {
      handlers.onDone?.({
        kind: "done",
        payload: { summary_id: "88", request_id: "7" },
        timestamp: new Date().toISOString(),
        correlation_id: "c1",
      } as StreamDoneEvent);
    });

    expect(result.current.isStreaming).toBe(false);
  });

  it("sets fellBack=true after two fatal onClose calls", async () => {
    const { result } = renderHook(() => useRequestStream(9));
    const handlers = captureHandlers();

    expect(result.current.fellBack).toBe(false);

    // First fatal close — below threshold (FALLBACK_THRESHOLD = 2).
    await act(async () => {
      handlers.onClose?.("fatal");
    });
    expect(result.current.fellBack).toBe(false);
    // isStreaming stays true while below threshold.
    expect(result.current.isStreaming).toBe(true);

    // Second fatal close — at threshold.
    await act(async () => {
      handlers.onClose?.("fatal");
    });
    expect(result.current.fellBack).toBe(true);
    expect(result.current.isStreaming).toBe(false);
  });

  it("manual onClose does not change isStreaming or fellBack", async () => {
    const { result } = renderHook(() => useRequestStream(10));
    const handlers = captureHandlers();

    await act(async () => {
      handlers.onClose?.("manual");
    });

    expect(result.current.isStreaming).toBe(true);
    expect(result.current.fellBack).toBe(false);
  });

  it("terminal onClose sets isStreaming=false without setting fellBack", async () => {
    const { result } = renderHook(() => useRequestStream(11));
    const handlers = captureHandlers();

    await act(async () => {
      handlers.onClose?.("terminal");
    });

    expect(result.current.isStreaming).toBe(false);
    expect(result.current.fellBack).toBe(false);
  });

  it("calls the cancel function on unmount", () => {
    const cancelFn = vi.fn();
    subscribeMock.mockReturnValue(cancelFn);

    const { unmount } = renderHook(() => useRequestStream(5));

    expect(cancelFn).not.toHaveBeenCalled();
    unmount();
    expect(cancelFn).toHaveBeenCalledTimes(1);
  });

  it("resets state and re-subscribes when requestId changes", async () => {
    subscribeMock.mockReturnValue(() => {});

    const { result, rerender } = renderHook(
      ({ id }: { id: number }) => useRequestStream(id),
      { initialProps: { id: 1 } },
    );

    // Drive some state on request 1.
    const handlers1 = captureHandlers();
    await act(async () => {
      handlers1.onPhase?.({
        kind: "phase",
        payload: { phase: "summarizing" },
        timestamp: new Date().toISOString(),
        correlation_id: "c",
      } as StreamPhaseEvent);
    });
    expect(result.current.phase).toBe("summarizing");

    // Switch to a different requestId.
    rerender({ id: 2 });

    // State must be reset.
    expect(result.current.phase).toBeNull();
    expect(result.current.isStreaming).toBe(true);
    expect(result.current.fellBack).toBe(false);
    // subscribeToRequest must have been called a second time.
    expect(subscribeMock).toHaveBeenCalledTimes(2);
    expect(subscribeMock.mock.calls[1][0]).toBe(2);
  });
});
