import { apiRequest } from "./client";

interface BackendPaginationInfo {
  total: number;
  limit: number;
  offset: number;
  hasMore?: boolean;
  has_more?: boolean;
}

interface BackendSyncEntity {
  entityType?: string;
  entity_type?: string;
  id: number | string;
  serverVersion?: number;
  server_version?: number;
  updatedAt?: string;
  updated_at?: string;
  deletedAt?: string | null;
  deleted_at?: string | null;
  summary?: Record<string, unknown> | null;
  request?: Record<string, unknown> | null;
  preference?: Record<string, unknown> | null;
  stat?: Record<string, unknown> | null;
  crawlResult?: Record<string, unknown> | null;
  crawl_result?: Record<string, unknown> | null;
  llmCall?: Record<string, unknown> | null;
  llm_call?: Record<string, unknown> | null;
}

interface BackendSyncSession {
  sessionId: string;
  expiresAt: string;
  defaultLimit: number;
  maxLimit: number;
  lastIssuedSince?: number | null;
}

interface BackendFullSync {
  sessionId: string;
  hasMore: boolean;
  nextSince?: number | null;
  items: BackendSyncEntity[];
  pagination: BackendPaginationInfo;
}

interface BackendDeltaSync {
  sessionId: string;
  since: number;
  hasMore: boolean;
  nextSince?: number | null;
  created: BackendSyncEntity[];
  updated: BackendSyncEntity[];
  deleted: BackendSyncEntity[];
}

interface BackendSyncApplyResult {
  entityType?: string;
  entity_type?: string;
  id: number | string;
  status: "applied" | "conflict" | "invalid";
  serverVersion?: number | null;
  server_version?: number | null;
  serverSnapshot?: Record<string, unknown> | null;
  server_snapshot?: Record<string, unknown> | null;
  errorCode?: string | null;
  error_code?: string | null;
}

interface BackendSyncApplyResponse {
  sessionId: string;
  results: BackendSyncApplyResult[];
  conflicts?: BackendSyncApplyResult[] | null;
  hasMore?: boolean | null;
}

export interface SyncPaginationInfo {
  total: number;
  limit: number;
  offset: number;
  has_more: boolean;
}

export interface SyncEntity {
  entity_type: string;
  id: number | string;
  server_version: number;
  updated_at: string;
  deleted_at: string | null;
  summary: Record<string, unknown> | null;
  request: Record<string, unknown> | null;
  preference: Record<string, unknown> | null;
  stat: Record<string, unknown> | null;
  crawl_result: Record<string, unknown> | null;
  llm_call: Record<string, unknown> | null;
}

export interface SyncSession {
  session_id: string;
  expires_at: string;
  default_limit: number;
  max_limit: number;
  last_issued_since: number | null;
}

export interface FullSyncChunk {
  session_id: string;
  has_more: boolean;
  next_since: number | null;
  items: SyncEntity[];
  pagination: SyncPaginationInfo;
}

export interface DeltaSyncChunk {
  session_id: string;
  since: number;
  has_more: boolean;
  next_since: number | null;
  created: SyncEntity[];
  updated: SyncEntity[];
  deleted: SyncEntity[];
}

export interface SyncApplyItemResult {
  entity_type: string;
  id: number | string;
  status: "applied" | "conflict" | "invalid";
  server_version: number | null;
  server_snapshot: Record<string, unknown> | null;
  error_code: string | null;
}

export interface SyncApplyResult {
  session_id: string;
  results: SyncApplyItemResult[];
  conflicts: SyncApplyItemResult[];
  has_more: boolean | null;
}

function mapPagination(pagination: BackendPaginationInfo): SyncPaginationInfo {
  return {
    total: pagination.total,
    limit: pagination.limit,
    offset: pagination.offset,
    has_more: Boolean(pagination.hasMore ?? pagination.has_more),
  };
}

function mapEntity(entity: BackendSyncEntity): SyncEntity {
  return {
    entity_type: entity.entityType ?? entity.entity_type ?? "",
    id: entity.id,
    server_version: entity.serverVersion ?? entity.server_version ?? 0,
    updated_at: entity.updatedAt ?? entity.updated_at ?? "",
    deleted_at: entity.deletedAt ?? entity.deleted_at ?? null,
    summary: entity.summary ?? null,
    request: entity.request ?? null,
    preference: entity.preference ?? null,
    stat: entity.stat ?? null,
    crawl_result: entity.crawlResult ?? entity.crawl_result ?? null,
    llm_call: entity.llmCall ?? entity.llm_call ?? null,
  };
}

function mapApplyResult(result: BackendSyncApplyResult): SyncApplyItemResult {
  return {
    entity_type: result.entityType ?? result.entity_type ?? "",
    id: result.id,
    status: result.status,
    server_version: result.serverVersion ?? result.server_version ?? null,
    server_snapshot: result.serverSnapshot ?? result.server_snapshot ?? null,
    error_code: result.errorCode ?? result.error_code ?? null,
  };
}

export function createSyncSession(limit?: number): Promise<SyncSession> {
  return apiRequest<BackendSyncSession>("/v1/sync/sessions", {
    method: "POST",
    body: JSON.stringify(limit ? { limit } : {}),
  }).then((payload) => ({
    session_id: payload.sessionId,
    expires_at: payload.expiresAt,
    default_limit: payload.defaultLimit,
    max_limit: payload.maxLimit,
    last_issued_since: payload.lastIssuedSince ?? null,
  }));
}

export function fetchFullSyncChunk(params: {
  session_id: string;
  limit?: number;
}): Promise<FullSyncChunk> {
  const q = new URLSearchParams({ session_id: params.session_id });
  if (params.limit !== undefined) q.set("limit", String(params.limit));
  return apiRequest<BackendFullSync>(`/v1/sync/full?${q}`).then((payload) => ({
    session_id: payload.sessionId,
    has_more: payload.hasMore,
    next_since: payload.nextSince ?? null,
    items: payload.items.map(mapEntity),
    pagination: mapPagination(payload.pagination),
  }));
}

export function fetchDeltaSyncChunk(params: {
  session_id: string;
  since: number;
  limit?: number;
}): Promise<DeltaSyncChunk> {
  const q = new URLSearchParams({
    session_id: params.session_id,
    since: String(params.since),
  });
  if (params.limit !== undefined) q.set("limit", String(params.limit));
  return apiRequest<BackendDeltaSync>(`/v1/sync/delta?${q}`).then((payload) => ({
    session_id: payload.sessionId,
    since: payload.since,
    has_more: payload.hasMore,
    next_since: payload.nextSince ?? null,
    created: payload.created.map(mapEntity),
    updated: payload.updated.map(mapEntity),
    deleted: payload.deleted.map(mapEntity),
  }));
}

export function applySyncChanges(params: {
  session_id: string;
  changes: Array<{
    entity_type: "summary" | "request" | "preference" | "stat" | "crawl_result" | "llm_call";
    id: number | string;
    action: "update" | "delete";
    last_seen_version: number;
    payload?: Record<string, unknown>;
    client_timestamp?: string;
  }>;
}): Promise<SyncApplyResult> {
  return apiRequest<BackendSyncApplyResponse>("/v1/sync/apply", {
    method: "POST",
    body: JSON.stringify({
      session_id: params.session_id,
      changes: params.changes,
    }),
  }).then((payload) => ({
    session_id: payload.sessionId,
    results: payload.results.map(mapApplyResult),
    conflicts: (payload.conflicts ?? []).map(mapApplyResult),
    has_more: payload.hasMore ?? null,
  }));
}
