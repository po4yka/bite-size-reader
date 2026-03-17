import { apiRequest } from "./client";

export interface DbInfo {
  file_size_mb: number;
  table_counts: Record<string, number>;
  db_path: string;
}

export function fetchDbInfo(): Promise<DbInfo> {
  return apiRequest("/v1/system/db-info");
}

export function clearCache(): Promise<{ cleared_keys: number }> {
  return apiRequest("/v1/system/clear-cache", { method: "POST" });
}

