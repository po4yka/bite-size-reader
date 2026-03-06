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
  type?: "url" | "forward";
  status: string;
  estimatedWaitSeconds?: number | null;
  createdAt?: string;
  isDuplicate?: boolean;
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
  request?: {
    id: number;
    type: string;
    status: string;
    correlationId?: string;
    inputUrl?: string | null;
    normalizedUrl?: string | null;
    createdAt?: string;
    langDetected?: string | null;
  } | null;
  crawlResult?: {
    status?: string | null;
    httpStatus?: number | null;
    latencyMs?: number | null;
    error?: string | null;
  } | null;
  llmCalls?: Array<{
    id: number;
    model?: string | null;
    status?: string | null;
    tokensPrompt?: number | null;
    tokensCompletion?: number | null;
    costUsd?: number | null;
    latencyMs?: number | null;
    createdAt?: string;
  }>;
  summary?: {
    id: number;
    status?: string;
    createdAt?: string;
  } | null;
}

interface RetryRequestBackendResponse {
  newRequestId: number;
  correlationId: string;
  status: string;
  createdAt: string;
}

export interface RequestDetail {
  id: string;
  type: string;
  status: string;
  correlation_id: string;
  input_url: string | null;
  normalized_url: string | null;
  created_at: string;
  lang_detected: string | null;
  crawl_result: {
    status: string | null;
    http_status: number | null;
    latency_ms: number | null;
    error: string | null;
  } | null;
  llm_calls: Array<{
    id: number;
    model: string | null;
    status: string | null;
    tokens_prompt: number | null;
    tokens_completion: number | null;
    cost_usd: number | null;
    latency_ms: number | null;
    created_at: string;
  }>;
  summary: {
    id: number;
    status: string;
    created_at: string;
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

function toSubmitResult(payload: SubmitRequestBackendResponse): {
  request_id: string;
  correlation_id: string;
  status: string;
} {
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
  }).then(toSubmitResult);
}

export function submitForwardContent(params: {
  content_text: string;
  from_chat_id: number;
  from_message_id: number;
  from_chat_title?: string;
  forwarded_at?: string;
  lang_preference?: "auto" | "en" | "ru";
}): Promise<{
  request_id: string;
  correlation_id: string;
  status: string;
}> {
  return apiRequest<SubmitRequestBackendResponse>("/v1/requests", {
    method: "POST",
    body: JSON.stringify({
      type: "forward",
      content_text: params.content_text,
      forward_metadata: {
        from_chat_id: params.from_chat_id,
        from_message_id: params.from_message_id,
        from_chat_title: params.from_chat_title ?? null,
        forwarded_at: params.forwarded_at ?? null,
      },
      lang_preference: params.lang_preference ?? "auto",
    }),
  }).then(toSubmitResult);
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

export async function fetchRequestDetail(requestId: string): Promise<RequestDetail> {
  const payload = await apiRequest<RequestDetailBackendResponse>(`/v1/requests/${requestId}`);
  const request = payload.request;
  if (!request) {
    throw new Error("Request details are missing from response");
  }

  return {
    id: String(request.id),
    type: request.type,
    status: request.status,
    correlation_id: request.correlationId ?? "",
    input_url: request.inputUrl ?? null,
    normalized_url: request.normalizedUrl ?? null,
    created_at: request.createdAt ?? "",
    lang_detected: request.langDetected ?? null,
    crawl_result: payload.crawlResult
      ? {
          status: payload.crawlResult.status ?? null,
          http_status: payload.crawlResult.httpStatus ?? null,
          latency_ms: payload.crawlResult.latencyMs ?? null,
          error: payload.crawlResult.error ?? null,
        }
      : null,
    llm_calls: (payload.llmCalls ?? []).map((call) => ({
      id: call.id,
      model: call.model ?? null,
      status: call.status ?? null,
      tokens_prompt: call.tokensPrompt ?? null,
      tokens_completion: call.tokensCompletion ?? null,
      cost_usd: call.costUsd ?? null,
      latency_ms: call.latencyMs ?? null,
      created_at: call.createdAt ?? "",
    })),
    summary: payload.summary
      ? {
          id: payload.summary.id,
          status: payload.summary.status ?? "",
          created_at: payload.summary.createdAt ?? "",
        }
      : null,
  };
}

export function retryRequest(requestId: string): Promise<{
  new_request_id: string;
  correlation_id: string;
  status: string;
  created_at: string;
}> {
  return apiRequest<RetryRequestBackendResponse>(`/v1/requests/${requestId}/retry`, {
    method: "POST",
  }).then((payload) => ({
    new_request_id: String(payload.newRequestId),
    correlation_id: payload.correlationId,
    status: payload.status,
    created_at: payload.createdAt,
  }));
}
