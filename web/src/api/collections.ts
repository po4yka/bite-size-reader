import { apiRequest } from "./client";
import { fetchSummary } from "./summaries";
import type { Collection, CollectionItem, PaginationInfo } from "./types";

interface CollectionPayload {
  id: number;
  name: string;
  parentId?: number | null;
  parent_id?: number | null;
  itemCount?: number;
  item_count?: number;
  children?: CollectionPayload[];
}

function mapCollection(raw: CollectionPayload): Collection {
  return {
    id: raw.id,
    name: raw.name,
    parentId: raw.parentId ?? raw.parent_id ?? null,
    itemCount: raw.itemCount ?? raw.item_count ?? 0,
    children: raw.children?.map(mapCollection),
  };
}

export async function fetchCollections(parentId?: number): Promise<{ collections: Collection[]; pagination: PaginationInfo }> {
  const q = new URLSearchParams();
  q.set("limit", "100");
  q.set("offset", "0");
  if (parentId != null) q.set("parent_id", String(parentId));

  const data = await apiRequest<{
    collections: CollectionPayload[];
    pagination: {
      total: number;
      limit: number;
      offset: number;
      hasMore?: boolean;
      has_more?: boolean;
    };
  }>(`/v1/collections?${q.toString()}`);

  return {
    collections: data.collections.map(mapCollection),
    pagination: {
      total: data.pagination.total,
      limit: data.pagination.limit,
      offset: data.pagination.offset,
      hasMore: Boolean(data.pagination.hasMore ?? data.pagination.has_more),
    },
  };
}

export async function fetchCollectionTree(): Promise<Collection[]> {
  const data = await apiRequest<{ collections: CollectionPayload[] }>("/v1/collections/tree");
  return data.collections.map(mapCollection);
}

export async function createCollection(name: string, parentId?: number): Promise<Collection> {
  const data = await apiRequest<CollectionPayload>("/v1/collections", {
    method: "POST",
    body: JSON.stringify({ name, parent_id: parentId ?? null }),
  });

  return mapCollection(data);
}

export async function fetchCollectionItems(collectionId: number): Promise<CollectionItem[]> {
  const data = await apiRequest<{
    items: Array<{
      collectionId?: number;
      collection_id?: number;
      summaryId?: number;
      summary_id?: number;
      position?: number;
      createdAt?: string;
      created_at?: string;
    }>;
  }>(`/v1/collections/${collectionId}/items?limit=100&offset=0`);

  const summaryIds = data.items
    .map((item) => item.summaryId ?? item.summary_id)
    .filter((id): id is number => typeof id === "number");

  const details = await Promise.allSettled(summaryIds.map((id) => fetchSummary(id)));
  const detailMap = new Map<number, Awaited<ReturnType<typeof fetchSummary>>>();
  details.forEach((result, index) => {
    const summaryId = summaryIds[index];
    if (result.status === "fulfilled" && summaryId != null) {
      detailMap.set(summaryId, result.value);
    }
  });

  return data.items.map((item) => {
    const summaryId = item.summaryId ?? item.summary_id ?? 0;
    const detail = detailMap.get(summaryId);
    return {
      id: summaryId,
      collectionId: item.collectionId ?? item.collection_id ?? collectionId,
      summaryId,
      position: item.position ?? 0,
      createdAt: item.createdAt ?? item.created_at ?? "",
      title: detail?.title,
      domain: detail?.domain,
    };
  });
}

export function addSummaryToCollection(collectionId: number, summaryId: number): Promise<{ success: boolean }> {
  return apiRequest<{ success: boolean }>(`/v1/collections/${collectionId}/items`, {
    method: "POST",
    body: JSON.stringify({ summary_id: summaryId }),
  });
}

export function removeSummaryFromCollection(collectionId: number, summaryId: number): Promise<{ success: boolean }> {
  return apiRequest<{ success: boolean }>(`/v1/collections/${collectionId}/items/${summaryId}`, {
    method: "DELETE",
  });
}
