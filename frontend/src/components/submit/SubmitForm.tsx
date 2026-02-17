import { useCallback, useEffect, useState } from "react";
import { checkDuplicate, submitUrl } from "../../api/requests";
import ProcessingStatus from "./ProcessingStatus";

interface SubmitFormProps {
  onViewArticle: (id: number) => void;
}

export default function SubmitForm({ onViewArticle }: SubmitFormProps) {
  const [url, setUrl] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [requestId, setRequestId] = useState<string | null>(null);
  const [duplicate, setDuplicate] = useState<{
    existing_request_id?: string;
    existing_summary_id?: number;
  } | null>(null);

  const handleBlur = useCallback(async () => {
    const trimmed = url.trim();
    if (!trimmed) return;

    try {
      const result = await checkDuplicate(trimmed);
      if (result.is_duplicate) {
        setDuplicate(result);
      } else {
        setDuplicate(null);
      }
    } catch {
      // Duplicate check is best-effort; ignore errors
    }
  }, [url]);

  const handleSubmit = useCallback(async (e?: React.FormEvent) => {
    e?.preventDefault();
    const trimmed = url.trim();
    if (!trimmed || submitting) return;

    window.Telegram?.WebApp?.HapticFeedback?.impactOccurred("medium");
    setSubmitting(true);
    setError("");
    setDuplicate(null);

    try {
      const result = await submitUrl(trimmed);
      setRequestId(result.request_id);
    } catch (err) {
      window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred("error");
      setError(err instanceof Error ? err.message : "Failed to submit URL");
    } finally {
      setSubmitting(false);
    }
  }, [url, submitting]);

  // Closing confirmation when URL input has content
  useEffect(() => {
    const wa = window.Telegram?.WebApp;
    if (!wa) return;
    if (url.trim() && !requestId) {
      wa.enableClosingConfirmation?.();
    } else {
      wa.disableClosingConfirmation?.();
    }
    return () => wa.disableClosingConfirmation?.();
  }, [url, requestId]);

  // MainButton integration
  useEffect(() => {
    const btn = window.Telegram?.WebApp?.MainButton;
    if (!btn) return;

    if (submitting) {
      btn.setText("Submitting...");
      btn.showProgress(true);
      btn.show();
      return () => { btn.hideProgress(); btn.hide(); };
    }

    if (url.trim() && !requestId) {
      btn.setText("Summarize");
      btn.show();
      const handler = () => handleSubmit();
      btn.onClick(handler);
      return () => { btn.offClick(handler); btn.hide(); };
    }

    btn.hide();
    return () => btn.hide();
  }, [url, submitting, requestId, handleSubmit]);

  const handleComplete = (summaryId: number) => {
    setRequestId(null);
    setUrl("");
    onViewArticle(summaryId);
  };

  const handleError = () => {
    setRequestId(null);
  };

  if (requestId) {
    return (
      <ProcessingStatus
        requestId={requestId}
        onComplete={handleComplete}
        onError={handleError}
      />
    );
  }

  return (
    <form className="submit-form" onSubmit={handleSubmit}>
      <input
        type="url"
        value={url}
        onChange={(e) => setUrl(e.target.value)}
        onBlur={handleBlur}
        placeholder="Paste an article or YouTube URL"
        disabled={submitting}
        aria-label="Article URL"
      />

      {duplicate?.existing_summary_id && (
        <div className="duplicate-notice">
          <span>This article has already been summarized.</span>
          <button
            type="button"
            className="btn-link"
            onClick={() => onViewArticle(duplicate.existing_summary_id!)}
          >
            View existing summary
          </button>
        </div>
      )}

      {error && <div className="error"><p>{error}</p></div>}

      <button type="submit" className="btn-primary" disabled={submitting || !url.trim()}>
        {submitting ? "Submitting..." : "Summarize"}
      </button>
    </form>
  );
}
