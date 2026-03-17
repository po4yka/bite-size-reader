import { apiRequest } from "./client";
import type { RequestStatus } from "./types";

const DEFAULT_PROGRESS_BY_STATUS: Record<RequestStatus["status"], number> = {
  pending: 10,
  crawling: 40,
  processing: 70,
  completed: 100,
  failed: 0,
};

export interface DuplicateCheckResult {
  isDuplicate: boolean;
  requestId: string | null;
  summaryId: number | null;
  normalizedUrl: string | null;
  summarizedAt: string | null;
}

// spec: components["schemas"]["DuplicateDetectionResponse"] (camelCase after normalizeKeys)
interface DuplicateCheckPayload {
  isDuplicate?: boolean;
  requestId?: number;
  summaryId?: number;
  normalizedUrl?: string | null;
  summarizedAt?: string | null;
}

// spec: components["schemas"]["SubmitRequestData"] (camelCase after normalizeKeys)
interface SubmitRequestPayload {
  requestId?: number;
  correlationId?: string;
  status?: string;
  estimatedWaitSeconds?: number | null;
  createdAt?: string | null;
}

interface SubmitPayload {
  request?: SubmitRequestPayload;
  isDuplicate?: boolean;
  existingRequestId?: number;
  existingSummaryId?: number;
  message?: string | null;
  summarizedAt?: string | null;
}

export interface SubmitQueuedResult {
  kind: "queued";
  requestId: string;
  status: string;
  correlationId: string;
  estimatedWaitSeconds: number | null;
  createdAt: string | null;
}

export interface SubmitDuplicateResult {
  kind: "duplicate";
  existingRequestId: string | null;
  existingSummaryId: number | null;
  message: string;
  summarizedAt: string | null;
}

export type SubmitUrlResult = SubmitQueuedResult | SubmitDuplicateResult;

// spec: components["schemas"]["RequestRetryResponseEnvelope"].data (snake_case — normalizeKeys converts)
interface RetryPayload {
  newRequestId?: number;
  correlationId?: string;
  status?: string;
  createdAt?: string;
}

// spec: components["schemas"]["RequestStatusData"] (camelCase)
interface StatusPayload {
  requestId?: number;
  status?: string;
  stage?: string;
  progress?: {
    percentage?: number;
  } | null;
  errorMessage?: string | null;
  canRetry?: boolean;
  retryable?: boolean | null;
  queuePosition?: number | null;
  estimatedSecondsRemaining?: number | null;
  correlationId?: string | null;
  updatedAt?: string | null;
  errorType?: string | null;
  errorReasonCode?: string | null;
}

interface RequestDetailPayload {
  summary?: {
    id?: number;
  } | null;
}

function normalizeStatus(payload: StatusPayload): RequestStatus["status"] {
  const stage = payload.stage ?? payload.status;
  if (stage === "complete" || stage === "completed" || payload.status === "success") return "completed";
  if (stage === "failed" || payload.status === "error") return "failed";
  if (stage === "crawling") return "crawling";
  if (stage === "processing") return "processing";
  return "pending";
}

function toSubmitResult(data: SubmitPayload): SubmitUrlResult {
  if (data.request) {
    const requestId = data.request.requestId;
    if (requestId == null) {
      throw new Error("Submit response is missing request id.");
    }

    return {
      kind: "queued",
      requestId: String(requestId),
      status: data.request.status ?? "pending",
      correlationId: data.request.correlationId ?? "",
      estimatedWaitSeconds: data.request.estimatedWaitSeconds ?? null,
      createdAt: data.request.createdAt ?? null,
    };
  }

  const isDuplicate = Boolean(data.isDuplicate);
  if (isDuplicate) {
    return {
      kind: "duplicate",
      existingRequestId: data.existingRequestId != null ? String(data.existingRequestId) : null,
      existingSummaryId: data.existingSummaryId ?? null,
      message: data.message ?? "This URL was already summarized.",
      summarizedAt: data.summarizedAt ?? null,
    };
  }

  throw new Error("Invalid submit response.");
}

function normalizeProgress(status: RequestStatus["status"], progressPct: number): number {
  if (Number.isFinite(progressPct) && progressPct > 0) {
    if (status === "completed") return 100;
    if (status === "failed") return Math.max(0, Math.min(100, progressPct));
    return Math.max(0, Math.min(95, progressPct));
  }
  return DEFAULT_PROGRESS_BY_STATUS[status];
}

export async function checkDuplicate(url: string): Promise<DuplicateCheckResult> {
  const data = await apiRequest<DuplicateCheckPayload>(`/v1/urls/check-duplicate?url=${encodeURIComponent(url)}`);

  return {
    isDuplicate: Boolean(data.isDuplicate),
    requestId: String(data.requestId ?? "") || null,
    summaryId: data.summaryId ?? null,
    normalizedUrl: data.normalizedUrl ?? null,
    summarizedAt: data.summarizedAt ?? null,
  };
}

export async function submitUrl(
  inputUrl: string,
  langPreference: "auto" | "en" | "ru" = "auto",
): Promise<SubmitUrlResult> {
  const data = await apiRequest<SubmitPayload>("/v1/requests", {
    method: "POST",
    body: JSON.stringify({
      input_url: inputUrl,
      lang_preference: langPreference,
    }),
  });
  return toSubmitResult(data);
}

export async function retryRequest(requestId: string): Promise<SubmitQueuedResult> {
  const data = await apiRequest<RetryPayload>(`/v1/requests/${requestId}/retry`, {
    method: "POST",
  });
  if (data.newRequestId == null) {
    throw new Error("Retry response is missing request id.");
  }
  return {
    kind: "queued",
    requestId: String(data.newRequestId),
    status: data.status ?? "pending",
    correlationId: data.correlationId ?? "",
    estimatedWaitSeconds: null,
    createdAt: data.createdAt ?? null,
  };
}

async function resolveSummaryId(requestId: string): Promise<number | null> {
  const detail = await apiRequest<RequestDetailPayload>(`/v1/requests/${requestId}`);
  return detail.summary?.id ?? null;
}

export async function fetchRequestStatus(requestId: string): Promise<RequestStatus> {
  const data = await apiRequest<StatusPayload>(`/v1/requests/${requestId}/status`);
  const normalizedStatus = normalizeStatus(data);
  const summaryId = normalizedStatus === "completed" ? await resolveSummaryId(requestId).catch(() => null) : null;
  const resolvedStatus = normalizedStatus === "completed" && summaryId == null ? "processing" : normalizedStatus;
  const rawProgress = Number(data.progress?.percentage ?? 0);

  return {
    requestId: String(data.requestId ?? requestId),
    status: resolvedStatus,
    progressPct: normalizeProgress(resolvedStatus, rawProgress),
    summaryId,
    errorMessage: data.errorMessage ?? null,
    queuePosition: data.queuePosition ?? null,
    estimatedSecondsRemaining: data.estimatedSecondsRemaining ?? null,
    canRetry: Boolean(data.canRetry),
    retryable: data.retryable ?? null,
    correlationId: data.correlationId ?? null,
    updatedAt: data.updatedAt ?? null,
    errorType: data.errorType ?? null,
    errorReasonCode: data.errorReasonCode ?? null,
  };
}
