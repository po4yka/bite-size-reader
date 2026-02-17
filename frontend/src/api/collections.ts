import { apiRequest } from "./client";
import type { Collection, CollectionItem, PaginationInfo } from "../types/api";

interface CollectionListResponse {
  collections: Collection[];
  pagination: PaginationInfo;
}

export function fetchCollections(parentId?: number): Promise<CollectionListResponse> {
  const q = new URLSearchParams();
  if (parentId) q.set("parent_id", String(parentId));
  q.set("limit", "100");
  const qs = q.toString();
  return apiRequest(`/v1/collections${qs ? `?${qs}` : ""}`);
}

export function fetchCollectionItems(id: number, limit = 20, offset = 0): Promise<{
  items: CollectionItem[];
  pagination: PaginationInfo;
}> {
  return apiRequest(`/v1/collections/${id}/items?limit=${limit}&offset=${offset}`);
}

export function createCollection(name: string, parentId?: number): Promise<Collection> {
  return apiRequest("/v1/collections", {
    method: "POST",
    body: JSON.stringify({ name, parent_id: parentId || null }),
  });
}

export function addToCollection(collectionId: number, summaryId: number): Promise<CollectionItem> {
  return apiRequest(`/v1/collections/${collectionId}/items`, {
    method: "POST",
    body: JSON.stringify({ summary_id: summaryId }),
  });
}

export function removeFromCollection(collectionId: number, itemId: number): Promise<void> {
  return apiRequest(`/v1/collections/${collectionId}/items/${itemId}`, {
    method: "DELETE",
  });
}
