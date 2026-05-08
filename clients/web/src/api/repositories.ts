import { apiRequest } from "./client";
import type { PaginationInfo } from "./types";

// Types matching backend Pydantic models EXACTLY
export type RepositoryListSort = "stars_desc" | "pushed_desc" | "created_desc" | "full_name_asc";
export type RepositorySource = "manual" | "starred";
export type Maturity = "prototype" | "alpha" | "beta" | "stable" | "mature" | "abandoned";
export type HallucinationRisk = "low" | "medium" | "high";

export interface RepositoryAnalysis {
  purpose: string;
  tech_stack: string[];
  architecture_summary: string;
  key_concepts: Array<{ term: string; explanation: string }>;
  code_patterns: Array<{ name: string; description: string }>;
  use_cases: string[];
  target_audience: string;
  maturity: Maturity;
  key_dependencies: string[];
  hallucination_risk: HallucinationRisk;
  confidence: number;
}

export interface RepositoryCompact {
  id: number;
  github_id: number;
  full_name: string;
  owner: string;
  name: string;
  description: string | null;
  primary_language: string | null;
  topics: string[];
  stars: number;
  forks: number;
  is_starred: boolean;
  is_archived: boolean;
  pushed_at: string | null;
  last_synced_at: string;
  pending_analysis: boolean;
  has_analysis: boolean;
  source: RepositorySource;
}

export interface RepositoryDetail extends RepositoryCompact {
  homepage_url: string | null;
  license_spdx: string | null;
  is_fork: boolean;
  is_template: boolean;
  languages: Record<string, number>;
  readme_excerpt: string | null;
  analysis: RepositoryAnalysis | null;
  analysis_model: string | null;
  analysis_at: string | null;
  content_hash: string | null;
  created_at_github: string | null;
  watchers: number;
}

export interface RepositoryListResponse {
  repositories: RepositoryCompact[];
  pagination: PaginationInfo;
}

export interface IngestRepositoryResponse {
  repository_id: number;
  status: "pending" | "ready";
  full_name: string;
}

export interface RepositorySearchHit extends RepositoryCompact {
  distance: number;
}

export interface RepositorySearchResponse {
  results: RepositorySearchHit[];
  pagination: PaginationInfo;
  query: string;
}

export interface FetchRepositoriesParams {
  is_starred?: boolean;
  language?: string;
  topic?: string;
  source?: RepositorySource;
  pending_analysis?: boolean;
  sort?: RepositoryListSort;
  limit?: number;
  offset?: number;
}

export async function fetchRepositories(params: FetchRepositoriesParams = {}): Promise<RepositoryListResponse> {
  const query = new URLSearchParams();
  if (params.is_starred !== undefined) query.set("is_starred", String(params.is_starred));
  if (params.language) query.set("language", params.language);
  if (params.topic) query.set("topic", params.topic);
  if (params.source) query.set("source", params.source);
  if (params.pending_analysis !== undefined) query.set("pending_analysis", String(params.pending_analysis));
  if (params.sort) query.set("sort", params.sort);
  if (params.limit !== undefined) query.set("limit", String(params.limit));
  if (params.offset !== undefined) query.set("offset", String(params.offset));
  return apiRequest<RepositoryListResponse>(`/v1/repositories?${query.toString()}`);
}

export async function fetchRepository(repositoryId: number): Promise<RepositoryDetail> {
  return apiRequest<RepositoryDetail>(`/v1/repositories/${repositoryId}`);
}

export async function ingestRepository(url: string): Promise<IngestRepositoryResponse> {
  return apiRequest<IngestRepositoryResponse>("/v1/repositories", {
    method: "POST",
    body: JSON.stringify({ url }),
  });
}

export async function reanalyzeRepository(repositoryId: number): Promise<RepositoryDetail> {
  return apiRequest<RepositoryDetail>(`/v1/repositories/${repositoryId}/reanalyze`, { method: "POST" });
}

export async function deleteRepository(repositoryId: number): Promise<void> {
  await apiRequest<void>(`/v1/repositories/${repositoryId}`, { method: "DELETE" });
}

export interface SearchRepositoriesParams {
  q: string;
  limit?: number;
  offset?: number;
  min_similarity?: number;
  languages?: string[];
  topics?: string[];
  is_starred?: boolean;
  source?: RepositorySource;
}

export async function searchRepositories(params: SearchRepositoriesParams): Promise<RepositorySearchResponse> {
  const query = new URLSearchParams();
  query.set("q", params.q);
  if (params.limit !== undefined) query.set("limit", String(params.limit));
  if (params.offset !== undefined) query.set("offset", String(params.offset));
  if (params.min_similarity !== undefined) query.set("min_similarity", String(params.min_similarity));
  if (params.languages) for (const l of params.languages) query.append("languages", l);
  if (params.topics) for (const t of params.topics) query.append("topics", t);
  if (params.is_starred !== undefined) query.set("is_starred", String(params.is_starred));
  if (params.source) query.set("source", params.source);
  return apiRequest<RepositorySearchResponse>(`/v1/search/repositories?${query.toString()}`);
}
