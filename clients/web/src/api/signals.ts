import { apiRequest } from "./client";

export type SignalStatus =
  | "candidate"
  | "queued"
  | "liked"
  | "dismissed"
  | "skipped"
  | "hidden_source"
  | "boosted_topic";

export type SignalFeedbackAction =
  | "like"
  | "dislike"
  | "skip"
  | "hide_source"
  | "queue"
  | "boost_topic";

export interface UserSignal {
  id: number;
  status: SignalStatus | string;
  heuristicScore: number | null;
  llmScore: number | null;
  finalScore: number | null;
  filterStage: string | null;
  evidenceJson?: Record<string, unknown> | null;
  llmJudgeJson?: Record<string, unknown> | null;
  llmCostUsd?: number | null;
  feedItemTitle: string | null;
  feedItemUrl: string | null;
  sourceKind: string | null;
  sourceTitle: string | null;
  topicName: string | null;
  createdAt?: string | null;
  updatedAt?: string | null;
}

export interface SignalSourceHealth {
  id: number;
  kind: string;
  externalId: string | null;
  url: string | null;
  title: string | null;
  isActive: boolean;
  fetchErrorCount: number;
  lastError: string | null;
  lastFetchedAt: string | null;
  lastSuccessfulAt: string | null;
  subscriptionId: number;
  subscriptionActive: boolean;
  cadenceSeconds: number | null;
  nextFetchAt: string | null;
}

export interface SignalHealth {
  chroma: {
    ready: boolean;
    required: boolean;
    collection: string | null;
  };
  sources: {
    total: number;
    active: number;
    errored: number;
  };
}

interface SignalsResponse {
  signals: UserSignal[];
}

interface SourceHealthResponse {
  sources: SignalSourceHealth[];
}

export function fetchSignals(): Promise<SignalsResponse> {
  return apiRequest<SignalsResponse>("/v1/signals");
}

export function fetchSignalHealth(): Promise<SignalHealth> {
  return apiRequest<SignalHealth>("/v1/signals/health");
}

export function fetchSignalSourceHealth(): Promise<SourceHealthResponse> {
  return apiRequest<SourceHealthResponse>("/v1/signals/sources/health");
}

export function updateSignalFeedback(
  signalId: number,
  action: SignalFeedbackAction,
): Promise<{ updated: boolean }> {
  return apiRequest<{ updated: boolean }>(`/v1/signals/${signalId}/feedback`, {
    method: "POST",
    body: JSON.stringify({ action }),
  });
}

export function setSignalSourceActive(
  sourceId: number,
  isActive: boolean,
): Promise<{ updated: boolean; isActive: boolean }> {
  return apiRequest<{ updated: boolean; isActive: boolean }>(
    `/v1/signals/sources/${sourceId}/active`,
    {
      method: "POST",
      body: JSON.stringify({ is_active: isActive }),
    },
  );
}

export function upsertSignalTopic(input: {
  name: string;
  description?: string | null;
  weight?: number;
}): Promise<{ topic: unknown }> {
  return apiRequest<{ topic: unknown }>("/v1/signals/topics", {
    method: "POST",
    body: JSON.stringify(input),
  });
}
