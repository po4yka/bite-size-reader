import { apiRequest } from "./client";
import type { RequestStatus } from "../types/api";

export function checkDuplicate(url: string): Promise<{
  is_duplicate: boolean;
  existing_request_id?: string;
  existing_summary_id?: number;
}> {
  return apiRequest(`/v1/search/urls/check-duplicate?url=${encodeURIComponent(url)}`);
}

export function submitUrl(url: string): Promise<{
  request_id: string;
  correlation_id: string;
  status: string;
}> {
  return apiRequest("/v1/requests", {
    method: "POST",
    body: JSON.stringify({ input_url: url }),
  });
}

export function pollStatus(requestId: string): Promise<RequestStatus> {
  return apiRequest(`/v1/requests/${requestId}/status`);
}
