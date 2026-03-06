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
