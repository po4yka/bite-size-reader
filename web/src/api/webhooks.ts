import { apiRequest } from "./client";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type WebhookEventType =
  | "summary.created"
  | "summary.updated"
  | "request.completed"
  | "request.failed"
  | "tag.attached"
  | "tag.detached"
  | "collection.item_added";

export const WEBHOOK_EVENT_TYPES: WebhookEventType[] = [
  "summary.created",
  "summary.updated",
  "request.completed",
  "request.failed",
  "tag.attached",
  "tag.detached",
  "collection.item_added",
];

export type WebhookStatus = "active" | "paused" | "disabled";

export interface Webhook {
  id: number;
  name: string | null;
  url: string;
  events: WebhookEventType[];
  status: WebhookStatus;
  failureCount: number;
  secretLast8: string;
  createdAt: string;
  updatedAt: string;
}

export interface WebhookDetail extends Webhook {
  secret?: string;
}

export interface WebhookDelivery {
  id: number;
  webhookId: number;
  eventType: string;
  statusCode: number | null;
  success: boolean;
  requestBody: string | null;
  responseBody: string | null;
  errorMessage: string | null;
  deliveredAt: string;
  durationMs: number | null;
}

export interface CreateWebhookPayload {
  name?: string;
  url: string;
  events: WebhookEventType[];
}

export interface UpdateWebhookPayload {
  name?: string | null;
  url?: string;
  events?: WebhookEventType[];
  status?: WebhookStatus;
}

// ---------------------------------------------------------------------------
// API functions
// ---------------------------------------------------------------------------

export async function fetchWebhooks(): Promise<Webhook[]> {
  const data = await apiRequest<{ webhooks: Webhook[] }>("/v1/webhooks");
  return data.webhooks;
}

export async function createWebhook(payload: CreateWebhookPayload): Promise<WebhookDetail> {
  return apiRequest<WebhookDetail>("/v1/webhooks", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function updateWebhook(id: number, payload: UpdateWebhookPayload): Promise<Webhook> {
  return apiRequest<Webhook>(`/v1/webhooks/${id}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function deleteWebhook(id: number): Promise<{ success: boolean }> {
  return apiRequest<{ success: boolean }>(`/v1/webhooks/${id}`, {
    method: "DELETE",
  });
}

export async function testWebhook(id: number): Promise<{ success: boolean; statusCode?: number; error?: string }> {
  return apiRequest<{ success: boolean; statusCode?: number; error?: string }>(`/v1/webhooks/${id}/test`, {
    method: "POST",
  });
}

export async function fetchDeliveries(
  id: number,
  limit = 20,
  offset = 0,
): Promise<{ deliveries: WebhookDelivery[] }> {
  const q = new URLSearchParams();
  q.set("limit", String(limit));
  q.set("offset", String(offset));
  return apiRequest<{ deliveries: WebhookDelivery[] }>(`/v1/webhooks/${id}/deliveries?${q.toString()}`);
}

export async function rotateSecret(id: number): Promise<{ secret: string }> {
  return apiRequest<{ secret: string }>(`/v1/webhooks/${id}/rotate-secret`, {
    method: "POST",
  });
}
