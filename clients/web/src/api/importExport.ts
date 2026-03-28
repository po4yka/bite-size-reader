import { apiRequest } from "./client";
import { config } from "../lib/config";
import { getApiSession } from "./session";

export interface ImportJobError {
  url: string;
  error: string;
}

export interface ImportJob {
  id: number;
  sourceFormat: string;
  fileName: string | null;
  status: string;
  totalItems: number;
  processedItems: number;
  createdItems: number;
  skippedItems: number;
  failedItems: number;
  errors: ImportJobError[];
  createdAt: string;
  updatedAt: string;
}

export interface ImportOptions {
  summarize?: boolean;
  createTags?: boolean;
  collectionId?: number;
}

export async function importFile(
  file: File,
  options: ImportOptions,
): Promise<ImportJob> {
  const formData = new FormData();
  formData.append("file", file);
  if (options.summarize != null) {
    formData.append("summarize", String(options.summarize));
  }
  if (options.createTags != null) {
    formData.append("create_tags", String(options.createTags));
  }
  if (options.collectionId != null) {
    formData.append("collection_id", String(options.collectionId));
  }

  return apiRequest<ImportJob>("/v1/import", {
    method: "POST",
    body: formData,
  });
}

export async function fetchImportJob(id: number): Promise<ImportJob> {
  return apiRequest<ImportJob>(`/v1/import/${id}`);
}

export async function fetchImportJobs(): Promise<ImportJob[]> {
  const data = await apiRequest<{ jobs: ImportJob[] }>("/v1/import");
  return data.jobs;
}

export async function deleteImportJob(
  id: number,
): Promise<{ success: boolean }> {
  return apiRequest<{ success: boolean }>(`/v1/import/${id}`, {
    method: "DELETE",
  });
}

export function getExportUrl(
  format: string,
  tag?: string,
  collectionId?: number,
): string {
  const params = new URLSearchParams({ format });
  if (tag) params.set("tag", tag);
  if (collectionId != null) params.set("collection_id", String(collectionId));

  const base = config.apiBaseUrl;
  const path = `/v1/export?${params.toString()}`;

  const session = getApiSession();
  if (session.mode === "jwt" && session.accessToken) {
    params.set("token", session.accessToken);
  }
  if (session.mode === "telegram-webapp" && session.initData) {
    params.set("init_data", session.initData);
  }

  return `${base}${path}`;
}
