import { apiRequest } from "./client";
import type { Highlight } from "./types";

interface HighlightsPayload {
  highlights: Array<Record<string, unknown>>;
}

function mapHighlight(raw: Record<string, unknown>): Highlight {
  return {
    id: String(raw.id ?? ""),
    text: String(raw.text ?? ""),
    startOffset: Number(raw.startOffset ?? 0),
    endOffset: Number(raw.endOffset ?? 0),
    color: raw.color != null ? String(raw.color) : null,
    note: raw.note != null ? String(raw.note) : null,
    createdAt: String(raw.createdAt ?? ""),
    updatedAt: String(raw.updatedAt ?? ""),
  };
}

export async function fetchHighlights(summaryId: number): Promise<Highlight[]> {
  const data = await apiRequest<HighlightsPayload>(`/v1/summaries/${summaryId}/highlights`);
  return (data.highlights ?? []).map(mapHighlight);
}

export interface CreateHighlightPayload {
  text: string;
  startOffset: number;
  endOffset: number;
  color?: string;
  note?: string;
}

export async function createHighlight(
  summaryId: number,
  payload: CreateHighlightPayload,
): Promise<Highlight> {
  const body: Record<string, unknown> = {
    text: payload.text,
    start_offset: payload.startOffset,
    end_offset: payload.endOffset,
  };
  if (payload.color !== undefined) body.color = payload.color;
  if (payload.note !== undefined) body.note = payload.note;

  const data = await apiRequest<Record<string, unknown>>(
    `/v1/summaries/${summaryId}/highlights`,
    { method: "POST", body: JSON.stringify(body) },
  );
  return mapHighlight(data);
}

export interface UpdateHighlightPayload {
  color?: string;
  note?: string;
}

export async function updateHighlight(
  summaryId: number,
  highlightId: string,
  payload: UpdateHighlightPayload,
): Promise<Highlight> {
  const data = await apiRequest<Record<string, unknown>>(
    `/v1/summaries/${summaryId}/highlights/${highlightId}`,
    { method: "PATCH", body: JSON.stringify(payload) },
  );
  return mapHighlight(data);
}

export async function deleteHighlight(
  summaryId: number,
  highlightId: string,
): Promise<void> {
  await apiRequest<unknown>(
    `/v1/summaries/${summaryId}/highlights/${highlightId}`,
    { method: "DELETE" },
  );
}
