import { apiRequest } from "./client";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface Condition {
  type: string;
  operator: string;
  value: string | string[] | number;
}

export interface Action {
  type: string;
  params: Record<string, unknown>;
}

export interface Rule {
  id: number;
  name: string;
  description: string | null;
  enabled: boolean;
  eventType: string;
  matchMode: string;
  conditions: Condition[];
  actions: Action[];
  priority: number;
  runCount: number;
  lastTriggeredAt: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface RuleLog {
  id: number;
  eventType: string;
  matched: boolean;
  conditionsResult: unknown[];
  actionsTaken: unknown[];
  error: string | null;
  durationMs: number | null;
  createdAt: string;
}

export interface CreateRulePayload {
  name: string;
  description?: string | null;
  enabled?: boolean;
  eventType: string;
  matchMode: string;
  conditions: Condition[];
  actions: Action[];
  priority?: number;
}

export interface UpdateRulePayload {
  name?: string;
  description?: string | null;
  enabled?: boolean;
  eventType?: string;
  matchMode?: string;
  conditions?: Condition[];
  actions?: Action[];
  priority?: number;
}

export const RULE_EVENT_TYPES = [
  "summary.created",
  "summary.updated",
  "tag.attached",
  "tag.detached",
  "request.completed",
  "request.failed",
  "collection.item_added",
] as const;

export type RuleEventType = (typeof RULE_EVENT_TYPES)[number];

export const CONDITION_TYPES = [
  "tag_name",
  "source_domain",
  "title_contains",
  "word_count",
  "language",
  "reading_time",
] as const;

export const CONDITION_OPERATORS: Record<string, string[]> = {
  tag_name: ["equals", "contains", "in"],
  source_domain: ["equals", "contains"],
  title_contains: ["contains", "matches"],
  word_count: ["gt", "lt", "eq", "gte", "lte"],
  language: ["equals", "in"],
  reading_time: ["gt", "lt", "eq", "gte", "lte"],
};

export const NUMERIC_CONDITION_TYPES = new Set(["word_count", "reading_time"]);

export const ACTION_TYPES = [
  "add_tag",
  "remove_tag",
  "add_to_collection",
  "set_favorite",
] as const;

// ---------------------------------------------------------------------------
// API functions
// ---------------------------------------------------------------------------

export async function fetchRules(): Promise<Rule[]> {
  const data = await apiRequest<{ rules: Rule[] }>("/v1/rules");
  return data.rules;
}

export async function createRule(payload: CreateRulePayload): Promise<Rule> {
  return apiRequest<Rule>("/v1/rules", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function updateRule(id: number, payload: UpdateRulePayload): Promise<Rule> {
  return apiRequest<Rule>(`/v1/rules/${id}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function deleteRule(id: number): Promise<{ success: boolean }> {
  return apiRequest<{ success: boolean }>(`/v1/rules/${id}`, {
    method: "DELETE",
  });
}

export async function testRule(
  id: number,
  summaryId: number,
): Promise<{ matched: boolean; conditionsResult: unknown[]; actionsTaken: unknown[] }> {
  return apiRequest<{ matched: boolean; conditionsResult: unknown[]; actionsTaken: unknown[] }>(
    `/v1/rules/${id}/test`,
    {
      method: "POST",
      body: JSON.stringify({ summary_id: summaryId }),
    },
  );
}

export async function fetchRuleLogs(
  id: number,
  limit = 20,
  offset = 0,
): Promise<{ logs: RuleLog[] }> {
  const q = new URLSearchParams();
  q.set("limit", String(limit));
  q.set("offset", String(offset));
  return apiRequest<{ logs: RuleLog[] }>(`/v1/rules/${id}/logs?${q.toString()}`);
}
