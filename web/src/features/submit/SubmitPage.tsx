import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  Button,
  InlineLoading,
  InlineNotification,
  ProgressBar,
  Select,
  SelectItem,
  TextInput,
  Tile,
} from "@carbon/react";
import { checkDuplicate, fetchRequestStatus, retryRequest, submitUrl } from "../../api/requests";
import { formatEta, isTerminalStatus, progressFromStatus, statusLabel } from "./status";
import { validateSubmitUrl } from "./url";

const DUPLICATE_DEBOUNCE_MS = 500;
const POLL_INTERVAL_MS = 2500;
const MAX_POLL_DURATION_MS = 6 * 60 * 1000;

interface DuplicateState {
  message: string;
  summaryId: number | null;
  requestId: string | null;
  summarizedAt: string | null;
}

export default function SubmitPage() {
  const navigate = useNavigate();

  const [url, setUrl] = useState("");
  const [langPreference, setLangPreference] = useState<"auto" | "en" | "ru">("auto");
  const [urlTouched, setUrlTouched] = useState(false);
  const [duplicateProbeUrl, setDuplicateProbeUrl] = useState("");
  const [requestId, setRequestId] = useState<string | null>(null);
  const [pollingPaused, setPollingPaused] = useState(false);
  const [pollingStartedAt, setPollingStartedAt] = useState<number | null>(null);
  const [submitDuplicate, setSubmitDuplicate] = useState<DuplicateState | null>(null);

  const urlValidation = useMemo(() => validateSubmitUrl(url), [url]);

  useEffect(() => {
    if (!urlValidation.isValid) {
      setDuplicateProbeUrl("");
      return;
    }
    const timer = window.setTimeout(() => {
      setDuplicateProbeUrl(urlValidation.normalizedUrl);
    }, DUPLICATE_DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [urlValidation.isValid, urlValidation.normalizedUrl]);

  const duplicateQuery = useQuery({
    queryKey: ["duplicate-check", duplicateProbeUrl],
    queryFn: () => checkDuplicate(duplicateProbeUrl),
    enabled: duplicateProbeUrl.length > 0 && requestId == null,
  });

  const submitMutation = useMutation({
    mutationFn: (payload: { inputUrl: string; langPreference: "auto" | "en" | "ru" }) =>
      submitUrl(payload.inputUrl, payload.langPreference),
    onMutate: () => {
      setRequestId(null);
      setPollingPaused(false);
      setPollingStartedAt(null);
      setSubmitDuplicate(null);
    },
    onSuccess: (result) => {
      if (result.kind === "queued") {
        setRequestId(result.requestId);
        setPollingPaused(false);
        setPollingStartedAt(Date.now());
        setSubmitDuplicate(null);
        return;
      }

      const duplicateState: DuplicateState = {
        message: result.message,
        summaryId: result.existingSummaryId,
        requestId: result.existingRequestId,
        summarizedAt: result.summarizedAt,
      };
      setSubmitDuplicate(duplicateState);

      if (!result.existingSummaryId && result.existingRequestId) {
        setRequestId(result.existingRequestId);
        setPollingPaused(false);
        setPollingStartedAt(Date.now());
      } else {
        setRequestId(null);
      }
    },
  });

  const statusQuery = useQuery({
    queryKey: ["request-status", requestId],
    queryFn: () => fetchRequestStatus(requestId ?? ""),
    enabled: Boolean(requestId) && !pollingPaused,
    retry: 2,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (!status) return POLL_INTERVAL_MS;
      return isTerminalStatus(status) ? false : POLL_INTERVAL_MS;
    },
  });

  const retryMutation = useMutation({
    mutationFn: () => retryRequest(requestId ?? ""),
    onSuccess: (result) => {
      setRequestId(result.requestId);
      setSubmitDuplicate(null);
      setPollingPaused(false);
      setPollingStartedAt(Date.now());
    },
  });

  useEffect(() => {
    if (!requestId || pollingPaused || isTerminalStatus(statusQuery.data?.status ?? "pending")) {
      return;
    }
    if (!pollingStartedAt) return;

    const remaining = MAX_POLL_DURATION_MS - (Date.now() - pollingStartedAt);
    if (remaining <= 0) {
      setPollingPaused(true);
      return;
    }

    const timer = window.setTimeout(() => {
      setPollingPaused(true);
    }, remaining);
    return () => window.clearTimeout(timer);
  }, [requestId, pollingPaused, pollingStartedAt, statusQuery.data?.status]);

  const progress = useMemo(() => {
    if (!statusQuery.data) return 0;
    return progressFromStatus(statusQuery.data.status, statusQuery.data.progressPct);
  }, [statusQuery.data]);

  const canSubmit = urlValidation.isValid && !submitMutation.isPending && !retryMutation.isPending;
  const duplicateSummaryId = submitDuplicate?.summaryId ?? (duplicateQuery.data?.isDuplicate ? duplicateQuery.data.summaryId : null);
  const duplicateRequestId = submitDuplicate?.requestId ?? (duplicateQuery.data?.isDuplicate ? duplicateQuery.data.requestId : null);

  const statusHelperParts = [
    statusQuery.data ? `Status: ${statusLabel(statusQuery.data.status)}` : null,
    statusQuery.data?.queuePosition ? `Queue position: ${statusQuery.data.queuePosition}` : null,
    formatEta(statusQuery.data?.estimatedSecondsRemaining),
  ].filter((part): part is string => Boolean(part));

  const statusHelperText = statusHelperParts.join(" · ");

  function startTrackingExistingRequest(): void {
    if (!duplicateRequestId) return;
    setRequestId(duplicateRequestId);
    setPollingPaused(false);
    setPollingStartedAt(Date.now());
  }

  function resetSubmitFlow(): void {
    setRequestId(null);
    setPollingPaused(false);
    setPollingStartedAt(null);
    setSubmitDuplicate(null);
  }

  return (
    <section className="page-section">
      <h1>Submit URL</h1>

      <Tile>
        <div className="digest-form-grid">
          <TextInput
            id="submit-url"
            labelText="Article or YouTube URL"
            placeholder="https://example.com/article"
            value={url}
            invalid={urlTouched && !urlValidation.isValid}
            invalidText={urlValidation.error ?? ""}
            onBlur={() => setUrlTouched(true)}
            onChange={(event) => {
              setUrl(event.currentTarget.value);
              setUrlTouched(true);
              if (!requestId) {
                setSubmitDuplicate(null);
              }
            }}
          />
          <Select
            id="submit-lang-preference"
            labelText="Summary language"
            value={langPreference}
            onChange={(event) => setLangPreference(event.currentTarget.value as "auto" | "en" | "ru")}
          >
            <SelectItem value="auto" text="Auto-detect" />
            <SelectItem value="en" text="English" />
            <SelectItem value="ru" text="Russian" />
          </Select>
        </div>

        <div className="form-actions">
          <Button
            onClick={() =>
              submitMutation.mutate({
                inputUrl: urlValidation.normalizedUrl,
                langPreference,
              })
            }
            disabled={!canSubmit}
          >
            {submitMutation.isPending ? "Submitting..." : "Summarize"}
          </Button>

          {duplicateSummaryId != null && (
            <Button kind="ghost" onClick={() => navigate(`/library/${duplicateSummaryId}`)}>
              View existing summary
            </Button>
          )}

          {duplicateSummaryId == null && duplicateRequestId && (
            <Button kind="tertiary" onClick={startTrackingExistingRequest}>
              Track existing request
            </Button>
          )}

          {(requestId || submitDuplicate) && (
            <Button kind="ghost" onClick={resetSubmitFlow}>
              Start new submission
            </Button>
          )}
        </div>

        {duplicateQuery.isFetching && !submitMutation.isPending && <InlineLoading description="Checking duplicates..." />}

        {submitMutation.error && (
          <InlineNotification
            kind="error"
            title="Submission failed"
            subtitle={submitMutation.error instanceof Error ? submitMutation.error.message : "Unknown error"}
            hideCloseButton
          />
        )}

        {duplicateQuery.error && !submitMutation.isPending && (
          <InlineNotification
            kind="warning"
            title="Duplicate pre-check unavailable"
            subtitle="You can still submit. We will validate on server side."
            hideCloseButton
          />
        )}

        {(submitDuplicate || duplicateQuery.data?.isDuplicate) && (
          <InlineNotification
            kind="info"
            title="Duplicate detected"
            subtitle={
              submitDuplicate?.message ??
              "This URL is already known. Open existing summary or track processing if still running."
            }
            hideCloseButton
          />
        )}

        {submitDuplicate?.summarizedAt && (
          <p className="muted">Already summarized on {new Date(submitDuplicate.summarizedAt).toLocaleString()}.</p>
        )}

        {requestId && statusQuery.data && (
          <>
            <ProgressBar label="Processing status" value={progress} helperText={statusHelperText || undefined} />

            <div className="form-actions">
              {statusQuery.data.status === "completed" && statusQuery.data.summaryId && (
                <Button onClick={() => navigate(`/library/${statusQuery.data.summaryId}`)}>Open summary</Button>
              )}

              {statusQuery.data.status === "failed" && (statusQuery.data.canRetry || statusQuery.data.retryable) && (
                <Button onClick={() => retryMutation.mutate()} disabled={retryMutation.isPending}>
                  {retryMutation.isPending ? "Retrying..." : "Retry processing"}
                </Button>
              )}

              {pollingPaused && (
                <Button kind="tertiary" onClick={() => setPollingPaused(false)}>
                  Resume polling
                </Button>
              )}

              <Button kind="ghost" onClick={() => void statusQuery.refetch()} disabled={statusQuery.isFetching}>
                Refresh now
              </Button>
            </div>

            {statusQuery.data.correlationId && (
              <p className="muted">Correlation ID: {statusQuery.data.correlationId}</p>
            )}

            {statusQuery.data.status === "failed" && (
              <InlineNotification
                kind="error"
                title="Processing failed"
                subtitle={statusQuery.data.errorMessage ?? "Unknown error"}
                hideCloseButton
              />
            )}
          </>
        )}

        {requestId && statusQuery.isLoading && <InlineLoading description="Connecting to status stream..." />}

        {requestId && statusQuery.error && (
          <InlineNotification
            kind="warning"
            title="Status polling interrupted"
            subtitle={statusQuery.error instanceof Error ? statusQuery.error.message : "Unknown error"}
            hideCloseButton
          />
        )}

        {pollingPaused && requestId && !isTerminalStatus(statusQuery.data?.status ?? "pending") && (
          <InlineNotification
            kind="warning"
            title="Polling paused"
            subtitle="Auto-polling was paused to prevent endless retries. Resume polling or refresh manually."
            hideCloseButton
          />
        )}
      </Tile>
    </section>
  );
}
