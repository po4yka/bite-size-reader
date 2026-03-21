import { apiRequest } from "./client";

// ---------------------------------------------------------------------------
// Existing types
// ---------------------------------------------------------------------------

export interface DbInfo {
  fileSizeMb: number;
  tableCounts: Record<string, number>;
  dbPath: string;
}

export interface ClearCacheResult {
  clearedKeys: number;
}

// ---------------------------------------------------------------------------
// Admin Users
// ---------------------------------------------------------------------------

export interface AdminUser {
  userId: number;
  username: string | null;
  isOwner: boolean;
  summaryCount: number;
  requestCount: number;
  tagCount: number;
  collectionCount: number;
  createdAt: string;
}

export interface AdminUsersResponse {
  users: AdminUser[];
  totalUsers: number;
}

// ---------------------------------------------------------------------------
// Admin Jobs
// ---------------------------------------------------------------------------

export interface PipelineStats {
  pending: number;
  processing: number;
  completedToday: number;
  failedToday: number;
}

export interface ImportStats {
  active: number;
  completedToday: number;
}

export interface JobsStatus {
  pipeline: PipelineStats;
  imports: ImportStats;
}

// ---------------------------------------------------------------------------
// Content Health
// ---------------------------------------------------------------------------

export interface RecentFailure {
  id: string;
  url: string;
  errorType: string | null;
  errorMessage: string | null;
  createdAt: string;
}

export interface ContentHealth {
  totalSummaries: number;
  totalRequests: number;
  failedRequests: number;
  failedByErrorType: Record<string, number>;
  recentFailures: RecentFailure[];
}

// ---------------------------------------------------------------------------
// System Metrics
// ---------------------------------------------------------------------------

export interface LlmStats {
  totalCalls: number;
  avgLatencyMs: number;
  totalPromptTokens: number;
  totalCompletionTokens: number;
  totalCostUsd: number;
  errorRate: number;
}

export interface ScraperProviderStats {
  total: number;
  success: number;
  successRate: number;
}

export interface SystemMetrics {
  database: DbInfo;
  llm7d: LlmStats;
  scraper7d: Record<string, ScraperProviderStats>;
}

// ---------------------------------------------------------------------------
// Audit Log
// ---------------------------------------------------------------------------

export interface AuditLogEntry {
  id: number;
  timestamp: string;
  level: string;
  event: string;
  details: Record<string, unknown> | null;
}

export interface AuditLogParams {
  action?: string;
  since?: string;
  limit?: number;
  offset?: number;
}

export interface AuditLogResponse {
  logs: AuditLogEntry[];
  total: number;
  limit: number;
  offset: number;
}

// ---------------------------------------------------------------------------
// API functions
// ---------------------------------------------------------------------------

export function fetchDbInfo(): Promise<DbInfo> {
  return apiRequest<DbInfo>("/v1/system/db-info");
}

export function clearCache(): Promise<ClearCacheResult> {
  return apiRequest<ClearCacheResult>("/v1/system/clear-cache", { method: "POST" });
}

export function fetchAdminUsers(): Promise<AdminUsersResponse> {
  return apiRequest<AdminUsersResponse>("/v1/admin/users");
}

export function fetchAdminJobs(): Promise<JobsStatus> {
  return apiRequest<JobsStatus>("/v1/admin/jobs");
}

export function fetchContentHealth(): Promise<ContentHealth> {
  return apiRequest<ContentHealth>("/v1/admin/health/content");
}

export function fetchMetrics(): Promise<SystemMetrics> {
  return apiRequest<SystemMetrics>("/v1/admin/metrics");
}

export function fetchAuditLog(params: AuditLogParams = {}): Promise<AuditLogResponse> {
  const searchParams = new URLSearchParams();
  if (params.action) searchParams.set("action", params.action);
  if (params.since) searchParams.set("since", params.since);
  if (params.limit != null) searchParams.set("limit", String(params.limit));
  if (params.offset != null) searchParams.set("offset", String(params.offset));

  const qs = searchParams.toString();
  return apiRequest<AuditLogResponse>(`/v1/admin/audit-log${qs ? `?${qs}` : ""}`);
}
