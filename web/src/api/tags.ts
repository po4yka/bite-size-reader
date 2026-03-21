import { apiRequest } from "./client";

export interface Tag {
  id: number;
  name: string;
  color: string | null;
  source: string;
  summaryCount: number;
  createdAt: string;
}

interface TagPayload {
  id: number;
  name: string;
  color?: string | null;
  source?: string;
  summaryCount?: number;
  createdAt?: string;
}

function mapTag(raw: TagPayload): Tag {
  return {
    id: raw.id,
    name: raw.name,
    color: raw.color ?? null,
    source: raw.source ?? "manual",
    summaryCount: raw.summaryCount ?? 0,
    createdAt: raw.createdAt ?? "",
  };
}

export async function fetchTags(): Promise<Tag[]> {
  const data = await apiRequest<{ tags: TagPayload[] }>("/v1/tags");
  return data.tags.map(mapTag);
}

export async function createTag(name: string, color?: string): Promise<Tag> {
  const data = await apiRequest<TagPayload>("/v1/tags", {
    method: "POST",
    body: JSON.stringify({ name, color: color ?? null }),
  });
  return mapTag(data);
}

export async function updateTag(
  tagId: number,
  payload: { name?: string; color?: string | null },
): Promise<Tag> {
  const data = await apiRequest<TagPayload>(`/v1/tags/${tagId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
  return mapTag(data);
}

export function deleteTag(tagId: number): Promise<{ success: boolean }> {
  return apiRequest<{ success: boolean }>(`/v1/tags/${tagId}`, {
    method: "DELETE",
  });
}

export function mergeTags(
  sourceTagIds: number[],
  targetTagId: number,
): Promise<{ success: boolean }> {
  return apiRequest<{ success: boolean }>("/v1/tags/merge", {
    method: "POST",
    body: JSON.stringify({ source_tag_ids: sourceTagIds, target_tag_id: targetTagId }),
  });
}

export function attachTags(
  summaryId: number,
  payload: { tagIds?: number[]; tagNames?: string[] },
): Promise<{ success: boolean }> {
  return apiRequest<{ success: boolean }>(`/v1/summaries/${summaryId}/tags`, {
    method: "POST",
    body: JSON.stringify({
      tag_ids: payload.tagIds ?? null,
      tag_names: payload.tagNames ?? null,
    }),
  });
}

export function detachTag(
  summaryId: number,
  tagId: number,
): Promise<{ success: boolean }> {
  return apiRequest<{ success: boolean }>(`/v1/summaries/${summaryId}/tags/${tagId}`, {
    method: "DELETE",
  });
}
