import { apiRequest } from "./client";
import type { SummaryCompact, SummaryDetail, SummaryContent, PaginationInfo } from "../types/api";

interface SummaryListResponse {
  summaries: SummaryCompact[];
  pagination: PaginationInfo;
}

export function fetchSummaries(params: {
  is_read?: boolean;
  is_favorite?: boolean;
  limit?: number;
  offset?: number;
  sort?: string;
} = {}): Promise<SummaryListResponse> {
  const q = new URLSearchParams();
  if (params.is_read !== undefined) q.set("is_read", String(params.is_read));
  if (params.is_favorite !== undefined) q.set("is_favorite", String(params.is_favorite));
  q.set("limit", String(params.limit ?? 20));
  q.set("offset", String(params.offset ?? 0));
  if (params.sort) q.set("sort", params.sort);
  return apiRequest(`/v1/summaries?${q}`);
}

export function fetchSummary(id: number): Promise<SummaryDetail> {
  return apiRequest(`/v1/summaries/${id}`);
}

export function fetchSummaryContent(id: number): Promise<SummaryContent> {
  return apiRequest(`/v1/summaries/${id}/content`);
}

export function markAsRead(id: number): Promise<SummaryCompact> {
  return apiRequest(`/v1/summaries/${id}`, {
    method: "PATCH",
    body: JSON.stringify({ is_read: true }),
  });
}

export function toggleFavorite(id: number): Promise<{ is_favorite: boolean }> {
  return apiRequest(`/v1/summaries/${id}/favorite`, { method: "POST" });
}
