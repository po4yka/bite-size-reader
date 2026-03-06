import { apiRequest } from "./client";
import type { Collection, CollectionItem, PaginationInfo } from "../types/api";
import { fetchSummary } from "./summaries";

interface CollectionListResponse {
  collections: Collection[];
  pagination: PaginationInfo;
}

interface BackendPaginationInfo {
  total: number;
  limit: number;
  offset: number;
  hasMore?: boolean;
  has_more?: boolean;
}

interface BackendCollection {
  id: number;
  name: string;
  parentId?: number | null;
  parent_id?: number | null;
  itemCount?: number | null;
  item_count?: number | null;
  createdAt?: string;
  created_at?: string;
  updatedAt?: string;
  updated_at?: string;
  children?: BackendCollection[];
}

interface BackendCollectionListResponse {
  collections: BackendCollection[];
  pagination?: BackendPaginationInfo;
}

interface BackendCollectionItem {
  collectionId?: number;
  collection_id?: number;
  summaryId?: number;
  summary_id?: number;
  position?: number | null;
  createdAt?: string;
  created_at?: string;
}

interface BackendCollectionItemsResponse {
  items: BackendCollectionItem[];
  pagination: BackendPaginationInfo;
}

interface BackendCollectionAclEntry {
  userId?: number | null;
  user_id?: number | null;
  role: "owner" | "editor" | "viewer";
  status: "active" | "pending" | "revoked";
  invitedBy?: number | null;
  invited_by?: number | null;
  createdAt?: string | null;
  created_at?: string | null;
  updatedAt?: string | null;
  updated_at?: string | null;
}

interface BackendCollectionAclResponse {
  acl: BackendCollectionAclEntry[];
}

interface BackendCollectionInviteResponse {
  token: string;
  role: "editor" | "viewer";
  expiresAt?: string | null;
  expires_at?: string | null;
}

interface BackendCollectionMoveResponse {
  id: number;
  parentId?: number | null;
  parent_id?: number | null;
  position: number;
  serverVersion?: number | null;
  server_version?: number | null;
  updatedAt?: string;
  updated_at?: string;
}

interface BackendCollectionItemsMoveResponse {
  movedSummaryIds?: number[];
  moved_summary_ids?: number[];
}

export interface CollectionAclEntry {
  user_id: number | null;
  role: "owner" | "editor" | "viewer";
  status: "active" | "pending" | "revoked";
  invited_by: number | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface CollectionMoveResult {
  id: number;
  parent_id: number | null;
  position: number;
  server_version: number | null;
  updated_at: string;
}

function mapPagination(pagination: BackendPaginationInfo): PaginationInfo {
  return {
    total: pagination.total,
    limit: pagination.limit,
    offset: pagination.offset,
    has_more: Boolean(pagination.hasMore ?? pagination.has_more),
  };
}

function mapCollection(collection: BackendCollection): Collection {
  const children = collection.children ?? [];
  return {
    id: collection.id,
    name: collection.name,
    parent_id: collection.parentId ?? collection.parent_id ?? null,
    item_count: collection.itemCount ?? collection.item_count ?? 0,
    children_count: children.length,
    created_at: collection.createdAt ?? collection.created_at ?? "",
    updated_at:
      collection.updatedAt ?? collection.updated_at ?? collection.createdAt ?? collection.created_at ?? "",
  };
}

function mapAclEntry(entry: BackendCollectionAclEntry): CollectionAclEntry {
  return {
    user_id: entry.userId ?? entry.user_id ?? null,
    role: entry.role,
    status: entry.status,
    invited_by: entry.invitedBy ?? entry.invited_by ?? null,
    created_at: entry.createdAt ?? entry.created_at ?? null,
    updated_at: entry.updatedAt ?? entry.updated_at ?? null,
  };
}

function toDomain(url: string): string {
  try {
    return new URL(url).hostname;
  } catch {
    return "";
  }
}

export function fetchCollections(parentId?: number): Promise<CollectionListResponse> {
  const q = new URLSearchParams();
  if (parentId != null) q.set("parent_id", String(parentId));
  q.set("limit", "100");
  const qs = q.toString();
  return apiRequest<BackendCollectionListResponse>(`/v1/collections${qs ? `?${qs}` : ""}`).then(
    (payload) => ({
      collections: payload.collections.map(mapCollection),
      pagination: payload.pagination
        ? mapPagination(payload.pagination)
        : { total: payload.collections.length, limit: 100, offset: 0, has_more: false },
    }),
  );
}

export async function fetchCollectionItems(id: number, limit = 20, offset = 0): Promise<{
  items: CollectionItem[];
  pagination: PaginationInfo;
}> {
  const payload = await apiRequest<BackendCollectionItemsResponse>(
    `/v1/collections/${id}/items?limit=${limit}&offset=${offset}`,
  );

  const summaryIds = payload.items
    .map((item) => item.summaryId ?? item.summary_id)
    .filter((summaryId): summaryId is number => typeof summaryId === "number");

  const details = await Promise.allSettled(summaryIds.map((summaryId) => fetchSummary(summaryId)));
  const detailsMap = new Map<number, Awaited<ReturnType<typeof fetchSummary>>>();
  details.forEach((result, idx) => {
    if (result.status === "fulfilled") {
      detailsMap.set(summaryIds[idx]!, result.value);
    }
  });

  const items: CollectionItem[] = payload.items.map((item) => {
    const summaryId = item.summaryId ?? item.summary_id ?? 0;
    const detail = detailsMap.get(summaryId);
    const url = detail?.url && detail.url.length > 0 ? detail.url : `https://example.com/s/${summaryId}`;
    return {
      id: summaryId,
      collection_id: item.collectionId ?? item.collection_id ?? id,
      summary_id: summaryId,
      title: detail?.title ?? `Summary #${summaryId}`,
      url,
      domain: detail?.domain || toDomain(url),
      tldr: detail?.tldr ?? "",
      topic_tags: detail?.topic_tags ?? [],
      added_at: item.createdAt ?? item.created_at ?? "",
      position: item.position ?? 0,
    };
  });

  return {
    items,
    pagination: mapPagination(payload.pagination),
  };
}

export function createCollection(name: string, parentId?: number): Promise<Collection> {
  return apiRequest<BackendCollection>("/v1/collections", {
    method: "POST",
    body: JSON.stringify({ name, parent_id: parentId || null }),
  }).then(mapCollection);
}

export function addToCollection(collectionId: number, summaryId: number): Promise<{ success: boolean }> {
  return apiRequest<{ success?: boolean }>(`/v1/collections/${collectionId}/items`, {
    method: "POST",
    body: JSON.stringify({ summary_id: summaryId }),
  }).then((payload) => ({
    success: Boolean(payload.success),
  }));
}

export function removeFromCollection(collectionId: number, summaryId: number): Promise<void> {
  return apiRequest(`/v1/collections/${collectionId}/items/${summaryId}`, {
    method: "DELETE",
  });
}

export function fetchCollection(collectionId: number): Promise<Collection> {
  return apiRequest<BackendCollection>(`/v1/collections/${collectionId}`).then(mapCollection);
}

export function updateCollection(
  collectionId: number,
  updates: {
    name?: string;
    description?: string | null;
    parent_id?: number | null;
    position?: number | null;
  },
): Promise<Collection> {
  return apiRequest<BackendCollection>(`/v1/collections/${collectionId}`, {
    method: "PATCH",
    body: JSON.stringify(updates),
  }).then(mapCollection);
}

export function deleteCollection(collectionId: number): Promise<{ success: boolean }> {
  return apiRequest<{ success?: boolean }>(`/v1/collections/${collectionId}`, {
    method: "DELETE",
  }).then((payload) => ({ success: Boolean(payload.success) }));
}

export function fetchCollectionTree(maxDepth = 3): Promise<{ collections: Collection[] }> {
  return apiRequest<{ collections: BackendCollection[] }>(`/v1/collections/tree?max_depth=${maxDepth}`).then(
    (payload) => ({
      collections: payload.collections.map(mapCollection),
    }),
  );
}

export function fetchCollectionAcl(collectionId: number): Promise<{ acl: CollectionAclEntry[] }> {
  return apiRequest<BackendCollectionAclResponse>(`/v1/collections/${collectionId}/acl`).then((payload) => ({
    acl: payload.acl.map(mapAclEntry),
  }));
}

export function shareCollection(
  collectionId: number,
  userId: number,
  role: "editor" | "viewer",
): Promise<{ success: boolean }> {
  return apiRequest<{ success?: boolean }>(`/v1/collections/${collectionId}/share`, {
    method: "POST",
    body: JSON.stringify({ user_id: userId, role }),
  }).then((payload) => ({ success: Boolean(payload.success) }));
}

export function removeCollectionCollaborator(
  collectionId: number,
  targetUserId: number,
): Promise<{ success: boolean }> {
  return apiRequest<{ success?: boolean }>(`/v1/collections/${collectionId}/share/${targetUserId}`, {
    method: "DELETE",
  }).then((payload) => ({ success: Boolean(payload.success) }));
}

export function createCollectionInvite(
  collectionId: number,
  role: "editor" | "viewer",
  expiresAt?: string,
): Promise<{ token: string; role: "editor" | "viewer"; expires_at: string | null }> {
  return apiRequest<BackendCollectionInviteResponse>(`/v1/collections/${collectionId}/invite`, {
    method: "POST",
    body: JSON.stringify({
      role,
      expires_at: expiresAt ?? null,
    }),
  }).then((payload) => ({
    token: payload.token,
    role: payload.role,
    expires_at: payload.expiresAt ?? payload.expires_at ?? null,
  }));
}

export function acceptCollectionInvite(token: string): Promise<{ success: boolean }> {
  return apiRequest<{ success?: boolean }>(`/v1/collections/invites/${encodeURIComponent(token)}/accept`, {
    method: "POST",
  }).then((payload) => ({ success: Boolean(payload.success) }));
}

export function reorderCollections(
  parentCollectionId: number,
  items: Array<{ collection_id: number; position: number }>,
): Promise<{ success: boolean }> {
  return apiRequest<{ success?: boolean }>(`/v1/collections/${parentCollectionId}/reorder`, {
    method: "POST",
    body: JSON.stringify({ items }),
  }).then((payload) => ({ success: Boolean(payload.success) }));
}

export function reorderCollectionItems(
  collectionId: number,
  items: Array<{ summary_id: number; position: number }>,
): Promise<{ success: boolean }> {
  return apiRequest<{ success?: boolean }>(`/v1/collections/${collectionId}/items/reorder`, {
    method: "POST",
    body: JSON.stringify({ items }),
  }).then((payload) => ({ success: Boolean(payload.success) }));
}

export function moveCollection(
  collectionId: number,
  target: { parent_id?: number | null; position?: number | null },
): Promise<CollectionMoveResult> {
  return apiRequest<BackendCollectionMoveResponse>(`/v1/collections/${collectionId}/move`, {
    method: "POST",
    body: JSON.stringify(target),
  }).then((payload) => ({
    id: payload.id,
    parent_id: payload.parentId ?? payload.parent_id ?? null,
    position: payload.position,
    server_version: payload.serverVersion ?? payload.server_version ?? null,
    updated_at: payload.updatedAt ?? payload.updated_at ?? "",
  }));
}

export function moveCollectionItems(
  collectionId: number,
  payload: {
    summary_ids: number[];
    target_collection_id: number;
    position?: number;
  },
): Promise<{ moved_summary_ids: number[] }> {
  return apiRequest<BackendCollectionItemsMoveResponse>(`/v1/collections/${collectionId}/items/move`, {
    method: "POST",
    body: JSON.stringify(payload),
  }).then((result) => ({
    moved_summary_ids: result.movedSummaryIds ?? result.moved_summary_ids ?? [],
  }));
}
