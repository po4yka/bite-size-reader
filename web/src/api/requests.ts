import { apiRequest } from "./client";
import type { RequestStatus } from "./types";

export async function checkDuplicate(url: string): Promise<{ isDuplicate: boolean; summaryId: number | null }> {
  const data = await apiRequest<{
    isDuplicate?: boolean;
    is_duplicate?: boolean;
    summaryId?: number;
    summary_id?: number;
  }>(`/v1/urls/check-duplicate?url=${encodeURIComponent(url)}`);

  return {
    isDuplicate: Boolean(data.isDuplicate ?? data.is_duplicate),
    summaryId: data.summaryId ?? data.summary_id ?? null,
  };
}

export async function submitUrl(inputUrl: string): Promise<{ requestId: string; status: string }> {
  const data = await apiRequest<{
    request?: {
      requestId?: number;
      request_id?: number;
      status?: string;
    };
  }>("/v1/requests", {
    method: "POST",
    body: JSON.stringify({ input_url: inputUrl }),
  });

  const requestId = data.request?.requestId ?? data.request?.request_id;
  return {
    requestId: String(requestId ?? ""),
    status: data.request?.status ?? "pending",
  };
}

interface StatusPayload {
  requestId?: number;
  request_id?: number;
  status?: string;
  stage?: string;
  progress?: {
    percentage?: number;
  };
  errorMessage?: string | null;
  error_message?: string | null;
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

async function resolveSummaryId(requestId: string): Promise<number | null> {
  const detail = await apiRequest<RequestDetailPayload>(`/v1/requests/${requestId}`);
  return detail.summary?.id ?? null;
}

export async function fetchRequestStatus(requestId: string): Promise<RequestStatus> {
  const data = await apiRequest<StatusPayload>(`/v1/requests/${requestId}/status`);
  const status = normalizeStatus(data);

  return {
    requestId: String(data.requestId ?? data.request_id ?? requestId),
    status,
    progressPct: Number(data.progress?.percentage ?? 0),
    summaryId: status === "completed" ? await resolveSummaryId(requestId).catch(() => null) : null,
    errorMessage: (data.errorMessage ?? data.error_message ?? null) as string | null,
  };
}
