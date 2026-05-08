import { useEffect, useRef, useState } from "react";
import { subscribeToRequest } from "../api/streamRequest";
import type { components } from "../api/generated";

type StreamPhaseEvent = components["schemas"]["StreamPhaseEvent"];
type StreamSectionEvent = components["schemas"]["StreamSectionEvent"];
type StreamErrorEvent = components["schemas"]["StreamErrorEvent"];

type Phase = StreamPhaseEvent["payload"]["phase"];

export interface UseRequestStreamResult {
  phase: Phase | null;
  sectionsBySlug: Record<string, string>;
  isStreaming: boolean;
  error: { code: string; message: string } | null;
  /** True if SSE has failed twice and we should fall back to polling. */
  fellBack: boolean;
}

const FALLBACK_THRESHOLD = 2;

export function useRequestStream(requestId: number | string | null): UseRequestStreamResult {
  const [phase, setPhase] = useState<Phase | null>(null);
  const [sectionsBySlug, setSectionsBySlug] = useState<Record<string, string>>({});
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<{ code: string; message: string } | null>(null);
  const [fellBack, setFellBack] = useState(false);

  // Track consecutive fatal closes to decide when to fall back
  const fatalCountRef = useRef(0);
  const cancelRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    if (requestId == null) return;

    // Reset state for new requestId
    setPhase(null);
    setSectionsBySlug({});
    setIsStreaming(true);
    setError(null);
    setFellBack(false);
    fatalCountRef.current = 0;

    const cancel = subscribeToRequest(requestId, {
      onPhase(event: StreamPhaseEvent) {
        setPhase(event.payload.phase);
      },

      onSection(event: StreamSectionEvent) {
        setSectionsBySlug((prev) => ({
          ...prev,
          [event.payload.section]: event.payload.content,
        }));
      },

      onDone() {
        setIsStreaming(false);
        fatalCountRef.current = 0;
      },

      onError(event: StreamErrorEvent) {
        setError({ code: event.payload.code, message: event.payload.message });
        setIsStreaming(false);
        fatalCountRef.current = 0;
      },

      onClose(cause) {
        if (cause === "manual") return;

        if (cause === "fatal") {
          fatalCountRef.current += 1;
          if (fatalCountRef.current >= FALLBACK_THRESHOLD) {
            setIsStreaming(false);
            setFellBack(true);
          }
          // Otherwise isStreaming stays true; subscribeToRequest will retry
        } else {
          // "terminal" — natural end of stream
          setIsStreaming(false);
        }
      },
    });

    cancelRef.current = cancel;

    return () => {
      cancelRef.current?.();
      cancelRef.current = null;
    };
  }, [requestId]);

  return { phase, sectionsBySlug, isStreaming, error, fellBack };
}
