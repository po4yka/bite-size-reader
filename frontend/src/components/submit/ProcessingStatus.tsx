import { useCallback, useEffect, useRef } from "react";
import { pollStatus } from "../../api/requests";
import { usePolling } from "../../hooks/usePolling";
import type { RequestStatus } from "../../types/api";

interface ProcessingStatusProps {
  requestId: string;
  onComplete: (summaryId: number) => void;
  onError: () => void;
}

const STATUS_PROGRESS: Record<string, number> = {
  pending: 10,
  crawling: 40,
  processing: 70,
  completed: 100,
};

const STATUS_LABELS: Record<string, string> = {
  pending: "Waiting in queue...",
  crawling: "Extracting content...",
  processing: "Generating summary...",
  completed: "Done!",
  failed: "Processing failed",
};

export default function ProcessingStatus({
  requestId,
  onComplete,
  onError,
}: ProcessingStatusProps) {
  const fetcher = useCallback(() => pollStatus(requestId), [requestId]);

  const shouldStop = useCallback(
    (d: RequestStatus) => d.status === "completed" || d.status === "failed",
    [],
  );

  const { data, error, loading, retry } = usePolling<RequestStatus>(
    fetcher,
    3000,
    true,
    shouldStop,
  );

  const calledRef = useRef(false);

  useEffect(() => {
    if (data?.status === "completed" && data.summary_id != null && !calledRef.current) {
      calledRef.current = true;
      onComplete(data.summary_id);
    }
  }, [data, onComplete]);

  const status = data?.status ?? "pending";
  const progress = STATUS_PROGRESS[status] ?? 0;
  const label = STATUS_LABELS[status] ?? status;

  if (data?.status === "failed") {
    return (
      <div className="processing-status">
        <div className="error">
          <p>{data.error_message ?? "An unexpected error occurred."}</p>
        </div>
        <button className="btn-retry" onClick={onError}>
          Try again
        </button>
      </div>
    );
  }

  return (
    <div className="processing-status">
      {loading && !data && <div className="loading">Connecting...</div>}

      {error && (
        <div className="error">
          <p>{error}</p>
          {retry && (
            <button className="btn-retry" onClick={retry}>
              Retry
            </button>
          )}
        </div>
      )}

      <div className="progress-bar">
        <div className="progress-bar-fill" style={{ width: `${progress}%` }} />
      </div>
      <div className="progress-label">{label}</div>
    </div>
  );
}
