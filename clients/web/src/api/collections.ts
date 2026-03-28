import { apiRequest } from "./client";
import { fetchSummary } from "./summaries";
import type { Collection, CollectionItem, PaginationInfo } from "./types";

interface CollectionPayload {
  id: number;
  name: string;
  description?: string | null;
  parentId?: number | null;
  position?: number | null;
  itemCount?: number;
  children?: CollectionPayload[];
  collectionType?: "manual" | "smart";
  queryConditions?: Array<{ type: string; operator: string; value: unknown }>;
  queryMatchMode?: "all" | "any";
  lastEvaluatedAt?: string | null;
}

function mapCollection(raw: CollectionPayload): Collection {
  return {
    id: raw.id,
    name: raw.name,
    description: raw.description ?? null,
    parentId: raw.parentId ?? null,
    position: raw.position ?? null,
    itemCount: raw.itemCount ?? 0,
    children: raw.children?.map(mapCollection),
    collectionType: raw.collectionType ?? "manual",
    queryConditions: raw.queryConditions,
    queryMatchMode: raw.queryMatchMode,
    lastEvaluatedAt: raw.lastEvaluatedAt ?? null,
  };
}

export async function fetchCollections(parentId?: number): Promise<{ collections: Collection[]; pagination: PaginationInfo }> {
  const q = new URLSearchParams();
  q.set("limit", "100");
  q.set("offset", "0");
  if (parentId != null) q.set("parent_id", String(parentId));

  const data = await apiRequest<{ collections: CollectionPayload[]; pagination: PaginationInfo }>(
    `/v1/collections?${q.toString()}`,
  );

  return {
    collections: data.collections.map(mapCollection),
    pagination: data.pagination,
  };
}

export async function fetchCollectionTree(): Promise<Collection[]> {
  const data = await apiRequest<{ collections: CollectionPayload[] }>("/v1/collections/tree");
  return data.collections.map(mapCollection);
}

export async function createCollection(
  name: string,
  parentId?: number,
  description?: string | null,
  smartFields?: {
    collection_type: "smart";
    query_conditions: Array<{ type: string; operator: string; value: unknown }>;
    query_match_mode: "all" | "any";
  },
): Promise<Collection> {
  const body: Record<string, unknown> = {
    name,
    description: description ?? null,
    parent_id: parentId ?? null,
  };
  if (smartFields) {
    body.collection_type = smartFields.collection_type;
    body.query_conditions = smartFields.query_conditions;
    body.query_match_mode = smartFields.query_match_mode;
  }
  const data = await apiRequest<CollectionPayload>("/v1/collections", {
    method: "POST",
    body: JSON.stringify(body),
  });

  return mapCollection(data);
}

export async function evaluateSmartCollection(
  collectionId: number,
): Promise<{ itemCount: number }> {
  return apiRequest<{ itemCount: number }>(
    `/v1/collections/${collectionId}/evaluate`,
    { method: "POST" },
  );
}

export async function fetchCollectionItems(collectionId: number): Promise<CollectionItem[]> {
  const data = await apiRequest<{
    items: Array<{
      collectionId?: number;
      summaryId?: number;
      position?: number;
      createdAt?: string;
    }>;
  }>(`/v1/collections/${collectionId}/items?limit=100&offset=0`);

  const summaryIds = data.items
    .map((item) => item.summaryId)
    .filter((id): id is number => typeof id === "number");

  const details = await Promise.allSettled(summaryIds.map((id) => fetchSummary(id)));
  const failed = details.filter((r) => r.status === "rejected").length;
  if (failed > 0) {
    console.warn(`[collections] Failed to load ${failed} item detail(s)`);
  }
  const detailMap = new Map<number, Awaited<ReturnType<typeof fetchSummary>>>();
  details.forEach((result, index) => {
    const summaryId = summaryIds[index];
    if (result.status === "fulfilled" && summaryId != null) {
      detailMap.set(summaryId, result.value);
    }
  });

  return data.items.map((item) => {
    const summaryId = item.summaryId ?? 0;
    const detail = detailMap.get(summaryId);
    return {
      id: summaryId,
      collectionId: item.collectionId ?? collectionId,
      summaryId,
      position: item.position ?? 0,
      createdAt: item.createdAt ?? "",
      title: detail?.title,
      domain: detail?.domain,
    };
  });
}

export async function updateCollection(
  collectionId: number,
  payload: {
    name?: string;
    description?: string | null;
    parent_id?: number | null;
    position?: number | null;
    query_conditions?: Array<{ type: string; operator: string; value: unknown }>;
    query_match_mode?: "all" | "any";
  },
): Promise<Collection> {
  const data = await apiRequest<CollectionPayload>(`/v1/collections/${collectionId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
  return mapCollection(data);
}

export function deleteCollection(collectionId: number): Promise<{ success: boolean }> {
  return apiRequest<{ success: boolean }>(`/v1/collections/${collectionId}`, {
    method: "DELETE",
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

export function moveCollectionItems(
  collectionId: number,
  summaryIds: number[],
  targetCollectionId: number,
  position?: number,
): Promise<{ movedSummaryIds: number[] }> {
  return apiRequest<{ movedSummaryIds: number[] }>(`/v1/collections/${collectionId}/items/move`, {
    method: "POST",
    body: JSON.stringify({
      summary_ids: summaryIds,
      target_collection_id: targetCollectionId,
      position: position ?? null,
    }),
  });
}

export function reorderCollectionItems(
  collectionId: number,
  items: Array<{ summary_id: number; position: number }>,
): Promise<{ success: boolean }> {
  return apiRequest<{ success: boolean }>(`/v1/collections/${collectionId}/items/reorder`, {
    method: "POST",
    body: JSON.stringify({ items }),
  });
}
