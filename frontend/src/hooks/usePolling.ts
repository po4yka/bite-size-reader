import { useCallback, useEffect, useRef, useState } from "react";

interface UsePollingResult<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
}

export function usePolling<T>(
  fetcher: () => Promise<T>,
  interval: number,
  shouldPoll: boolean,
): UsePollingResult<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(shouldPoll);
  const fetcherRef = useRef(fetcher);

  useEffect(() => {
    fetcherRef.current = fetcher;
  }, [fetcher]);

  const tick = useCallback(async () => {
    try {
      const result = await fetcherRef.current();
      setData(result);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Polling failed");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!shouldPoll) return;

    setLoading(true);
    tick();

    const id = setInterval(tick, interval);
    return () => clearInterval(id);
  }, [shouldPoll, interval, tick]);

  return { data, error, loading };
}
