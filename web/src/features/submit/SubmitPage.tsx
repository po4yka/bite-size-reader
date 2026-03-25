import { useCallback, useEffect, useMemo, useReducer, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Button,
  ContentSwitcher,
  InlineLoading,
  InlineNotification,
  ProgressBar,
  Select,
  SelectItem,
  Switch,
  TextInput,
  Tile,
} from "@carbon/react";
import { useDuplicateCheck, useRequestStatus, useSubmitUrl, useRetryRequest } from "../../hooks/useRequests";
import { useTelegramClosingConfirmation } from "../../hooks/useTelegramClosingConfirmation";
import { useTelegramMainButton } from "../../hooks/useTelegramMainButton";
import { formatEta, isTerminalStatus, progressFromStatus, statusLabel } from "./status";
import { validateSubmitUrl } from "./url";
import { ForwardForm } from "./ForwardForm";

const DUPLICATE_DEBOUNCE_MS = 500;
const MAX_POLL_DURATION_MS = 6 * 60 * 1000;

interface DuplicateState {
  message: string;
  summaryId: number | null;
  requestId: string | null;
  summarizedAt: string | null;
}

type SubmitMode = "url" | "forward";

// ---------------------------------------------------------------------------
// Submission state machine
// ---------------------------------------------------------------------------

type SubmissionPhase = "idle" | "submitting" | "polling" | "completed" | "error";

interface SubmissionState {
  phase: SubmissionPhase;
  requestId: string | null;
  pollingPaused: boolean;
  pollingStartedAt: number | null;
  submitDuplicate: DuplicateState | null;
}

type SubmissionAction =
  | { type: "SUBMIT_START" }
  | { type: "SUBMIT_SUCCESS"; requestId: string; pollingStartedAt: number }
  | {
      type: "SUBMIT_DUPLICATE";
      duplicate: DuplicateState;
      requestId: string | null;
      pollingStartedAt: number | null;
    }
  | { type: "POLL_PAUSE" }
  | { type: "POLL_RESUME" }
  | { type: "PROCESSING_COMPLETE" }
  | { type: "SUBMIT_ERROR" }
  | { type: "RESET" };

const initialSubmissionState: SubmissionState = {
  phase: "idle",
  requestId: null,
  pollingPaused: false,
  pollingStartedAt: null,
  submitDuplicate: null,
};

function submissionReducer(state: SubmissionState, action: SubmissionAction): SubmissionState {
  switch (action.type) {
    case "SUBMIT_START":
      return {
        ...initialSubmissionState,
        phase: "submitting",
      };
    case "SUBMIT_SUCCESS":
      return {
        ...state,
        phase: "polling",
        requestId: action.requestId,
        pollingPaused: false,
        pollingStartedAt: action.pollingStartedAt,
        submitDuplicate: null,
      };
    case "SUBMIT_DUPLICATE":
      return {
        ...state,
        phase: action.requestId != null ? "polling" : "completed",
        requestId: action.requestId,
        pollingPaused: false,
        pollingStartedAt: action.pollingStartedAt,
        submitDuplicate: action.duplicate,
      };
    case "POLL_PAUSE":
      return { ...state, pollingPaused: true };
    case "POLL_RESUME":
      return { ...state, pollingPaused: false };
    case "PROCESSING_COMPLETE":
      return { ...state, phase: "completed" };
    case "SUBMIT_ERROR":
      return { ...state, phase: "error" };
    case "RESET":
      return { ...initialSubmissionState };
    default:
      return state;
  }
}

export default function SubmitPage() {
  const navigate = useNavigate();

  const [submitMode, setSubmitMode] = useState<SubmitMode>("url");
  const [url, setUrl] = useState("");
  const [langPreference, setLangPreference] = useState<"auto" | "en" | "ru">("auto");
  const [urlTouched, setUrlTouched] = useState(false);
  const [duplicateProbeUrl, setDuplicateProbeUrl] = useState("");
  const [submission, dispatchSubmission] = useReducer(submissionReducer, initialSubmissionState);
  const { requestId, pollingPaused, pollingStartedAt, submitDuplicate } = submission;

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

  const duplicateQuery = useDuplicateCheck(duplicateProbeUrl, duplicateProbeUrl.length > 0 && requestId == null);
  const submitMutation = useSubmitUrl();
  const statusQuery = useRequestStatus(requestId, pollingPaused);
  const retryMutation = useRetryRequest();

  useEffect(() => {
    if (!requestId || pollingPaused || isTerminalStatus(statusQuery.data?.status ?? "pending")) {
      return;
    }
    if (!pollingStartedAt) return;

    const remaining = MAX_POLL_DURATION_MS - (Date.now() - pollingStartedAt);
    if (remaining <= 0) {
      dispatchSubmission({ type: "POLL_PAUSE" });
      return;
    }

    const timer = window.setTimeout(() => {
      dispatchSubmission({ type: "POLL_PAUSE" });
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
  const completedSummaryId =
    statusQuery.data?.status === "completed" ? (statusQuery.data.summaryId ?? null) : null;
  const canRetryStatus = Boolean(
    statusQuery.data?.status === "failed" && (statusQuery.data.canRetry || statusQuery.data.retryable),
  );
  const isFormDirty =
    url.trim().length > 0 ||
    langPreference !== "auto" ||
    requestId != null ||
    submitDuplicate != null ||
    submitMutation.isPending ||
    retryMutation.isPending;

  useTelegramClosingConfirmation(isFormDirty);

  const handleSubmit = useCallback(() => {
    if (!canSubmit) return;
    dispatchSubmission({ type: "SUBMIT_START" });
    submitMutation.mutate(
      { inputUrl: urlValidation.normalizedUrl, langPreference },
      {
        onSuccess: (result) => {
          if (result.kind === "queued") {
            dispatchSubmission({
              type: "SUBMIT_SUCCESS",
              requestId: result.requestId,
              pollingStartedAt: Date.now(),
            });
            return;
          }
          const duplicateState: DuplicateState = {
            message: result.message,
            summaryId: result.existingSummaryId,
            requestId: result.existingRequestId,
            summarizedAt: result.summarizedAt,
          };
          if (!result.existingSummaryId && result.existingRequestId) {
            dispatchSubmission({
              type: "SUBMIT_DUPLICATE",
              duplicate: duplicateState,
              requestId: result.existingRequestId,
              pollingStartedAt: Date.now(),
            });
          } else {
            dispatchSubmission({
              type: "SUBMIT_DUPLICATE",
              duplicate: duplicateState,
              requestId: null,
              pollingStartedAt: null,
            });
          }
        },
      },
    );
  }, [canSubmit, langPreference, submitMutation, urlValidation.normalizedUrl]);

  const handleOpenCompletedSummary = useCallback(() => {
    if (!completedSummaryId) return;
    navigate(`/library/${completedSummaryId}`);
  }, [completedSummaryId, navigate]);

  const handleRetry = useCallback(() => {
    if (!canRetryStatus || retryMutation.isPending || !requestId) return;
    retryMutation.mutate(requestId, {
      onSuccess: (result) => {
        dispatchSubmission({
          type: "SUBMIT_SUCCESS",
          requestId: result.requestId,
          pollingStartedAt: Date.now(),
        });
      },
    });
  }, [canRetryStatus, retryMutation, requestId]);

  useTelegramMainButton({
    visible: requestId == null || completedSummaryId != null || canRetryStatus,
    text: completedSummaryId != null ? "Open Summary" : canRetryStatus ? "Retry Processing" : "Summarize",
    disabled:
      completedSummaryId != null
        ? false
        : canRetryStatus
          ? retryMutation.isPending
          : !canSubmit,
    loading: submitMutation.isPending || retryMutation.isPending,
    onClick: completedSummaryId != null ? handleOpenCompletedSummary : canRetryStatus ? handleRetry : handleSubmit,
  });

  function startTrackingExistingRequest(): void {
    if (!duplicateRequestId) return;
    dispatchSubmission({
      type: "SUBMIT_SUCCESS",
      requestId: duplicateRequestId,
      pollingStartedAt: Date.now(),
    });
  }

  function resetSubmitFlow(): void {
    dispatchSubmission({ type: "RESET" });
  }

  return (
    <section className="page-section">
      <h1>Submit</h1>

      <div style={{ marginBottom: "1rem" }}>
        <ContentSwitcher
          selectedIndex={submitMode === "url" ? 0 : 1}
          onChange={({ index }) => {
            setSubmitMode(index === 0 ? "url" : "forward");
            dispatchSubmission({ type: "RESET" });
          }}
        >
          <Switch name="url" text="URL" />
          <Switch name="forward" text="Forward" />
        </ContentSwitcher>
      </div>

      {submitMode === "forward" && (
        <>
          <ForwardForm
            onRequestCreated={(id) => {
              dispatchSubmission({
                type: "SUBMIT_SUCCESS",
                requestId: id,
                pollingStartedAt: Date.now(),
              });
            }}
          />
          {requestId && statusQuery.data && (
            <Tile style={{ marginTop: "1rem" }}>
              <ProgressBar label="Processing status" value={progress} helperText={statusHelperText || undefined} />
              <div className="form-actions">
                {statusQuery.data.status === "completed" && statusQuery.data.summaryId && (
                  <Button onClick={handleOpenCompletedSummary}>Open summary</Button>
                )}
                {statusQuery.data.status === "failed" && (statusQuery.data.canRetry || statusQuery.data.retryable) && (
                  <Button onClick={handleRetry} disabled={retryMutation.isPending}>
                    {retryMutation.isPending ? "Retrying..." : "Retry processing"}
                  </Button>
                )}
                {pollingPaused && (
                  <Button kind="tertiary" onClick={() => dispatchSubmission({ type: "POLL_RESUME" })}>
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
            </Tile>
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
        </>
      )}

      {submitMode === "url" && (
      <Tile>
        <div className="digest-form-grid">
          <TextInput
            id="submit-url"
            labelText="Article or YouTube URL"
            placeholder="https://example.com/article…"
            value={url}
            invalid={urlTouched && !urlValidation.isValid}
            invalidText={urlValidation.error ?? ""}
            onBlur={() => setUrlTouched(true)}
            onChange={(event) => {
              setUrl(event.currentTarget.value);
              setUrlTouched(true);
              if (!requestId) {
                dispatchSubmission({ type: "RESET" });
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
            onClick={handleSubmit}
            disabled={!canSubmit}
          >
            {submitMutation.isPending ? "Submitting…" : "Summarize"}
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

        {duplicateQuery.isFetching && !submitMutation.isPending && <InlineLoading description="Checking duplicates…" />}

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
                <Button onClick={handleOpenCompletedSummary}>Open summary</Button>
              )}

              {statusQuery.data.status === "failed" && (statusQuery.data.canRetry || statusQuery.data.retryable) && (
                <Button onClick={handleRetry} disabled={retryMutation.isPending}>
                  {retryMutation.isPending ? "Retrying…" : "Retry processing"}
                </Button>
              )}

              {pollingPaused && (
                <Button kind="tertiary" onClick={() => dispatchSubmission({ type: "POLL_RESUME" })}>
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

        {requestId && statusQuery.isLoading && <InlineLoading description="Connecting to status stream…" />}

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
      )}
    </section>
  );
}
