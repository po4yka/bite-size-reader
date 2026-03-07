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

interface DuplicateCheckPayload {
  isDuplicate?: boolean;
  is_duplicate?: boolean;
  requestId?: number;
  request_id?: number;
  summaryId?: number;
  summary_id?: number;
  normalizedUrl?: string | null;
  normalized_url?: string | null;
  summarizedAt?: string | null;
  summarized_at?: string | null;
}

interface SubmitRequestPayload {
  requestId?: number;
  request_id?: number;
  correlationId?: string;
  correlation_id?: string;
  status?: string;
  estimatedWaitSeconds?: number | null;
  estimated_wait_seconds?: number | null;
  createdAt?: string | null;
  created_at?: string | null;
}

interface SubmitPayload {
  request?: SubmitRequestPayload;
  isDuplicate?: boolean;
  is_duplicate?: boolean;
  existingRequestId?: number;
  existing_request_id?: number;
  existingSummaryId?: number;
  existing_summary_id?: number;
  message?: string | null;
  summarizedAt?: string | null;
  summarized_at?: string | null;
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

interface RetryPayload {
  newRequestId?: number;
  new_request_id?: number;
  correlationId?: string;
  correlation_id?: string;
  status?: string;
  createdAt?: string;
  created_at?: string;
}

interface StatusPayload {
  requestId?: number;
  request_id?: number;
  status?: string;
  stage?: string;
  progress?: {
    percentage?: number;
  } | null;
  errorMessage?: string | null;
  error_message?: string | null;
  canRetry?: boolean;
  can_retry?: boolean;
  retryable?: boolean | null;
  queuePosition?: number | null;
  queue_position?: number | null;
  estimatedSecondsRemaining?: number | null;
  estimated_seconds_remaining?: number | null;
  correlationId?: string | null;
  correlation_id?: string | null;
  updatedAt?: string | null;
  updated_at?: string | null;
  errorType?: string | null;
  error_type?: string | null;
  errorReasonCode?: string | null;
  error_reason_code?: string | null;
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
    const requestId = data.request.requestId ?? data.request.request_id;
    if (requestId == null) {
      throw new Error("Submit response is missing request id.");
    }

    return {
      kind: "queued",
      requestId: String(requestId),
      status: data.request.status ?? "pending",
      correlationId: data.request.correlationId ?? data.request.correlation_id ?? "",
      estimatedWaitSeconds:
        data.request.estimatedWaitSeconds ?? data.request.estimated_wait_seconds ?? null,
      createdAt: data.request.createdAt ?? data.request.created_at ?? null,
    };
  }

  const isDuplicate = Boolean(data.isDuplicate ?? data.is_duplicate);
  if (isDuplicate) {
    const existingRequestId = data.existingRequestId ?? data.existing_request_id;
    return {
      kind: "duplicate",
      existingRequestId: existingRequestId != null ? String(existingRequestId) : null,
      existingSummaryId: data.existingSummaryId ?? data.existing_summary_id ?? null,
      message: data.message ?? "This URL was already summarized.",
      summarizedAt: data.summarizedAt ?? data.summarized_at ?? null,
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
    isDuplicate: Boolean(data.isDuplicate ?? data.is_duplicate),
    requestId: String(data.requestId ?? data.request_id ?? "") || null,
    summaryId: data.summaryId ?? data.summary_id ?? null,
    normalizedUrl: data.normalizedUrl ?? data.normalized_url ?? null,
    summarizedAt: data.summarizedAt ?? data.summarized_at ?? null,
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
  const newRequestId = data.newRequestId ?? data.new_request_id;
  if (newRequestId == null) {
    throw new Error("Retry response is missing request id.");
  }
  return {
    kind: "queued",
    requestId: String(newRequestId),
    status: data.status ?? "pending",
    correlationId: data.correlationId ?? data.correlation_id ?? "",
    estimatedWaitSeconds: null,
    createdAt: data.createdAt ?? data.created_at ?? null,
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
    requestId: String(data.requestId ?? data.request_id ?? requestId),
    status: resolvedStatus,
    progressPct: normalizeProgress(resolvedStatus, rawProgress),
    summaryId,
    errorMessage: (data.errorMessage ?? data.error_message ?? null) as string | null,
    queuePosition: data.queuePosition ?? data.queue_position ?? null,
    estimatedSecondsRemaining: data.estimatedSecondsRemaining ?? data.estimated_seconds_remaining ?? null,
    canRetry: Boolean(data.canRetry ?? data.can_retry),
    retryable: data.retryable ?? null,
    correlationId: data.correlationId ?? data.correlation_id ?? null,
    updatedAt: data.updatedAt ?? data.updated_at ?? null,
    errorType: data.errorType ?? data.error_type ?? null,
    errorReasonCode: data.errorReasonCode ?? data.error_reason_code ?? null,
  };
}
