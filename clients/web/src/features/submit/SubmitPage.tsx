import { useCallback, useEffect, useMemo, useReducer, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  BracketButton,
  ContentSwitcher,
  MonoInput,
  MonoSelect,
  MonoSelectItem,
  MonoProgressBar,
  SparkLoading,
  StatusBadge,
  Switch,
} from "../../design";
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
    <main
      style={{
        maxWidth: "var(--frost-strip-5)",
        padding: "0 var(--frost-pad-page)",
        display: "flex",
        flexDirection: "column",
        gap: "var(--frost-gap-section)",
      }}
    >
      <h1
        style={{
          fontFamily: "var(--frost-font-mono)",
          fontSize: "var(--frost-type-mono-emph-size)",
          fontWeight: "var(--frost-type-mono-emph-weight)" as React.CSSProperties["fontWeight"],
          letterSpacing: "var(--frost-type-mono-emph-tracking)",
          textTransform: "uppercase",
          color: "var(--frost-ink)",
          margin: 0,
        }}
      >
        Submit
      </h1>

      <div>
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
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            gap: "var(--frost-gap-section)",
          }}
        >
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
            <div
              style={{
                border: "1px solid var(--frost-ink)",
                padding: "var(--frost-pad-page)",
                display: "flex",
                flexDirection: "column",
                gap: "var(--frost-gap-row)",
              }}
            >
              <p
                style={{
                  fontFamily: "var(--frost-font-mono)",
                  fontSize: "11px",
                  fontWeight: 800,
                  textTransform: "uppercase",
                  letterSpacing: "1px",
                  color: "color-mix(in oklch, var(--frost-ink) 55%, transparent)",
                  margin: 0,
                }}
              >
                § STATUS
              </p>
              <MonoProgressBar label="Processing status" value={progress} helperText={statusHelperText || undefined} />
              <div style={{ display: "flex", gap: "var(--frost-gap-row)", flexWrap: "wrap" }}>
                {statusQuery.data.status === "completed" && statusQuery.data.summaryId && (
                  <BracketButton onClick={handleOpenCompletedSummary}>Open summary</BracketButton>
                )}
                {statusQuery.data.status === "failed" && (statusQuery.data.canRetry || statusQuery.data.retryable) && (
                  <BracketButton onClick={handleRetry} disabled={retryMutation.isPending}>
                    {retryMutation.isPending ? "Retrying..." : "Retry processing"}
                  </BracketButton>
                )}
                {pollingPaused && (
                  <BracketButton kind="ghost" onClick={() => dispatchSubmission({ type: "POLL_RESUME" })}>
                    Resume polling
                  </BracketButton>
                )}
                <BracketButton kind="ghost" onClick={() => void statusQuery.refetch()} disabled={statusQuery.isFetching}>
                  Refresh now
                </BracketButton>
              </div>
              {statusQuery.data.correlationId && (
                <p
                  style={{
                    fontFamily: "var(--frost-font-mono)",
                    fontSize: "var(--frost-type-mono-xs-size)",
                    color: "color-mix(in oklch, var(--frost-ink) 55%, transparent)",
                    margin: 0,
                  }}
                >
                  Correlation ID: {statusQuery.data.correlationId}
                </p>
              )}
              {statusQuery.data.status === "failed" && (
                <StatusBadge severity="alarm" title="Processing failed" subtitle={statusQuery.data.errorMessage ?? "Unknown error"} />
              )}
            </div>
          )}
          {requestId && statusQuery.isLoading && <SparkLoading description="Connecting to status stream..." />}
          {requestId && statusQuery.error && (
            <StatusBadge
              severity="warn"
              title="Status polling interrupted"
              subtitle={statusQuery.error instanceof Error ? statusQuery.error.message : "Unknown error"}
            />
          )}
        </div>
      )}

      {submitMode === "url" && (
        <div
          style={{
            border: "1px solid var(--frost-ink)",
            padding: "var(--frost-pad-page)",
            display: "flex",
            flexDirection: "column",
            gap: "var(--frost-gap-section)",
          }}
        >
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              gap: "var(--frost-gap-row)",
            }}
          >
            <p
              style={{
                fontFamily: "var(--frost-font-mono)",
                fontSize: "11px",
                fontWeight: 800,
                textTransform: "uppercase",
                letterSpacing: "1px",
                color: "color-mix(in oklch, var(--frost-ink) 55%, transparent)",
                margin: 0,
              }}
            >
              § SUBMIT URL
            </p>
            <MonoInput
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
            <MonoSelect
              id="submit-lang-preference"
              labelText="Summary language"
              value={langPreference}
              onChange={(event) => setLangPreference(event.currentTarget.value as "auto" | "en" | "ru")}
            >
              <MonoSelectItem value="auto" text="Auto-detect" />
              <MonoSelectItem value="en" text="English" />
              <MonoSelectItem value="ru" text="Russian" />
            </MonoSelect>
          </div>

          <div style={{ display: "flex", gap: "var(--frost-gap-row)", flexWrap: "wrap" }}>
            <BracketButton
              onClick={handleSubmit}
              disabled={!canSubmit}
            >
              {submitMutation.isPending ? "Submitting…" : "Summarize"}
            </BracketButton>

            {duplicateSummaryId != null && (
              <BracketButton kind="ghost" onClick={() => navigate(`/library/${duplicateSummaryId}`)}>
                View existing summary
              </BracketButton>
            )}

            {duplicateSummaryId == null && duplicateRequestId && (
              <BracketButton kind="ghost" onClick={startTrackingExistingRequest}>
                Track existing request
              </BracketButton>
            )}

            {(requestId || submitDuplicate) && (
              <BracketButton kind="ghost" onClick={resetSubmitFlow}>
                Start new submission
              </BracketButton>
            )}
          </div>

          {duplicateQuery.isFetching && !submitMutation.isPending && (
            <SparkLoading description="Checking duplicates…" />
          )}

          {submitMutation.error && (
            <StatusBadge
              severity="alarm"
              title="Submission failed"
              subtitle={submitMutation.error instanceof Error ? submitMutation.error.message : "Unknown error"}
            />
          )}

          {duplicateQuery.error && !submitMutation.isPending && (
            <StatusBadge
              severity="warn"
              title="Duplicate pre-check unavailable"
              subtitle="You can still submit. We will validate on server side."
            />
          )}

          {(submitDuplicate || duplicateQuery.data?.isDuplicate) && (
            <StatusBadge
              severity="info"
              title="✓ Duplicate detected"
              subtitle={
                submitDuplicate?.message ??
                "This URL is already known. Open existing summary or track processing if still running."
              }
            />
          )}

          {submitDuplicate?.summarizedAt && (
            <p
              style={{
                fontFamily: "var(--frost-font-mono)",
                fontSize: "var(--frost-type-mono-xs-size)",
                color: "color-mix(in oklch, var(--frost-ink) 55%, transparent)",
                margin: 0,
              }}
            >
              Already summarized on {new Date(submitDuplicate.summarizedAt).toLocaleString()}.
            </p>
          )}

          {requestId && statusQuery.data && (
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                gap: "var(--frost-gap-row)",
              }}
            >
              <p
                style={{
                  fontFamily: "var(--frost-font-mono)",
                  fontSize: "11px",
                  fontWeight: 800,
                  textTransform: "uppercase",
                  letterSpacing: "1px",
                  color: "color-mix(in oklch, var(--frost-ink) 55%, transparent)",
                  margin: 0,
                }}
              >
                § STATUS
              </p>
              <MonoProgressBar label="Processing status" value={progress} helperText={statusHelperText || undefined} />

              <div style={{ display: "flex", gap: "var(--frost-gap-row)", flexWrap: "wrap" }}>
                {statusQuery.data.status === "completed" && statusQuery.data.summaryId && (
                  <BracketButton onClick={handleOpenCompletedSummary}>Open summary</BracketButton>
                )}

                {statusQuery.data.status === "failed" && (statusQuery.data.canRetry || statusQuery.data.retryable) && (
                  <BracketButton onClick={handleRetry} disabled={retryMutation.isPending}>
                    {retryMutation.isPending ? "Retrying…" : "Retry processing"}
                  </BracketButton>
                )}

                {pollingPaused && (
                  <BracketButton kind="ghost" onClick={() => dispatchSubmission({ type: "POLL_RESUME" })}>
                    Resume polling
                  </BracketButton>
                )}

                <BracketButton kind="ghost" onClick={() => void statusQuery.refetch()} disabled={statusQuery.isFetching}>
                  Refresh now
                </BracketButton>
              </div>

              {statusQuery.data.correlationId && (
                <p
                  style={{
                    fontFamily: "var(--frost-font-mono)",
                    fontSize: "var(--frost-type-mono-xs-size)",
                    color: "color-mix(in oklch, var(--frost-ink) 55%, transparent)",
                    margin: 0,
                  }}
                >
                  Correlation ID: {statusQuery.data.correlationId}
                </p>
              )}

              {statusQuery.data.status === "failed" && (
                <StatusBadge
                  severity="alarm"
                  title="Processing failed"
                  subtitle={statusQuery.data.errorMessage ?? "Unknown error"}
                />
              )}
            </div>
          )}

          {requestId && statusQuery.isLoading && (
            <SparkLoading description="Connecting to status stream…" />
          )}

          {requestId && statusQuery.error && (
            <StatusBadge
              severity="warn"
              title="Status polling interrupted"
              subtitle={statusQuery.error instanceof Error ? statusQuery.error.message : "Unknown error"}
            />
          )}

          {pollingPaused && requestId && !isTerminalStatus(statusQuery.data?.status ?? "pending") && (
            <StatusBadge
              severity="warn"
              title="Polling paused"
              subtitle="Auto-polling was paused to prevent endless retries. Resume polling or refresh manually."
            />
          )}
        </div>
      )}
    </main>
  );
}
