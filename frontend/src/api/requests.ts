import { apiRequest } from "./client";
import type { RequestStatus } from "../types/api";

interface DuplicateCheckBackendResponse {
  is_duplicate: boolean;
  request_id?: number;
  summary_id?: number;
  existing_request_id?: number;
  existing_summary_id?: number;
}

interface SubmitRequestPayload {
  requestId: number;
  correlationId: string;
  status: string;
}

interface SubmitRequestBackendResponse {
  request?: SubmitRequestPayload;
  isDuplicate?: boolean;
  existingRequestId?: number;
  existingSummaryId?: number;
  message?: string;
}

interface RequestStatusBackendResponse {
  requestId: number;
  status: string;
  stage: string;
  progress?: {
    percentage?: number;
  } | null;
  errorMessage?: string | null;
  updatedAt: string;
}

interface RequestDetailBackendResponse {
  summary?: {
    id: number;
  } | null;
}

const DEFAULT_PROGRESS_BY_STAGE: Record<string, number> = {
  pending: 10,
  crawling: 40,
  processing: 70,
  complete: 100,
  failed: 0,
};

function toFrontendStatus(stage: string, status: string): RequestStatus["status"] {
  if (stage === "complete" || status === "success") return "completed";
  if (stage === "failed" || status === "error") return "failed";
  if (stage === "crawling") return "crawling";
  if (stage === "processing") return "processing";
  return "pending";
}

export function checkDuplicate(url: string): Promise<{
  is_duplicate: boolean;
  existing_request_id?: string;
  existing_summary_id?: number;
}> {
  return apiRequest<DuplicateCheckBackendResponse>(
    `/v1/urls/check-duplicate?url=${encodeURIComponent(url)}`,
  ).then((payload) => ({
    is_duplicate: Boolean(payload.is_duplicate),
    existing_request_id: String(
      payload.request_id ?? payload.existing_request_id ?? "",
    ) || undefined,
    existing_summary_id: payload.summary_id ?? payload.existing_summary_id,
  }));
}

export function submitUrl(url: string): Promise<{
  request_id: string;
  correlation_id: string;
  status: string;
}> {
  return apiRequest<SubmitRequestBackendResponse>("/v1/requests", {
    method: "POST",
    body: JSON.stringify({ input_url: url }),
  }).then((payload) => {
    if (payload.request) {
      return {
        request_id: String(payload.request.requestId),
        correlation_id: payload.request.correlationId,
        status: payload.request.status,
      };
    }

    if (payload.isDuplicate && payload.existingRequestId != null) {
      return {
        request_id: String(payload.existingRequestId),
        correlation_id: "",
        status: "completed",
      };
    }

    throw new Error(payload.message ?? "Invalid submit response");
  });
}

async function resolveSummaryId(requestId: number): Promise<number | null> {
  const detail = await apiRequest<RequestDetailBackendResponse>(`/v1/requests/${requestId}`);
  return detail.summary?.id ?? null;
}

export async function pollStatus(requestId: string): Promise<RequestStatus> {
  const payload = await apiRequest<RequestStatusBackendResponse>(`/v1/requests/${requestId}/status`);
  const frontendStatus = toFrontendStatus(payload.stage, payload.status);
  const numericRequestId = Number(requestId);
  const safeRequestId = Number.isFinite(numericRequestId) ? numericRequestId : payload.requestId;
  const summaryId = frontendStatus === "completed"
    ? await resolveSummaryId(safeRequestId).catch(() => null)
    : null;
  const resolvedStatus = frontendStatus === "completed" && summaryId == null
    ? "processing"
    : frontendStatus;

  return {
    id: String(payload.requestId),
    status: resolvedStatus,
    progress_pct: payload.progress?.percentage ?? DEFAULT_PROGRESS_BY_STAGE[payload.stage] ?? 0,
    summary_id: summaryId,
    error_message: payload.errorMessage ?? null,
    created_at: payload.updatedAt,
    updated_at: payload.updatedAt,
  };
}
