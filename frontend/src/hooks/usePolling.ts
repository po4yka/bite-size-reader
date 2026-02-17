import { useCallback, useEffect, useRef, useState } from "react";

const MAX_CONSECUTIVE_ERRORS = 5;

interface UsePollingResult<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
  retry: (() => void) | null;
}

export function usePolling<T>(
  fetcher: () => Promise<T>,
  interval: number,
  shouldPoll: boolean,
  shouldStop?: (data: T) => boolean,
): UsePollingResult<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(shouldPoll);
  const fetcherRef = useRef(fetcher);
  const shouldStopRef = useRef(shouldStop);
  const stoppedRef = useRef(false);
  const consecutiveErrors = useRef(0);
  const intervalIdRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    fetcherRef.current = fetcher;
  }, [fetcher]);

  useEffect(() => {
    shouldStopRef.current = shouldStop;
  }, [shouldStop]);

  const tick = useCallback(async () => {
    if (stoppedRef.current) return;
    try {
      const result = await fetcherRef.current();
      setData(result);
      setError(null);
      consecutiveErrors.current = 0;
      if (shouldStopRef.current?.(result)) {
        stoppedRef.current = true;
        if (intervalIdRef.current != null) {
          clearInterval(intervalIdRef.current);
          intervalIdRef.current = null;
        }
      }
    } catch (e) {
      consecutiveErrors.current++;
      if (consecutiveErrors.current >= MAX_CONSECUTIVE_ERRORS) {
        stoppedRef.current = true;
        setError("Connection lost. Tap to retry.");
        if (intervalIdRef.current != null) {
          clearInterval(intervalIdRef.current);
          intervalIdRef.current = null;
        }
      } else {
        setError(e instanceof Error ? e.message : "Polling failed");
      }
    } finally {
      setLoading(false);
    }
  }, []);

  const startPolling = useCallback(() => {
    stoppedRef.current = false;
    consecutiveErrors.current = 0;
    setError(null);
    setLoading(true);
    tick();
    intervalIdRef.current = setInterval(tick, interval);
  }, [tick, interval]);

  useEffect(() => {
    if (!shouldPoll) return;
    startPolling();
    return () => {
      if (intervalIdRef.current != null) {
        clearInterval(intervalIdRef.current);
        intervalIdRef.current = null;
      }
    };
  }, [shouldPoll, startPolling]);

  const retry = stoppedRef.current && error
    ? () => startPolling()
    : null;

  return { data, error, loading, retry };
}
