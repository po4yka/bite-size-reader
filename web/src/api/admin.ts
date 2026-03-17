import { apiRequest } from "./client";

export interface DbInfo {
  fileSizeMb: number;
  tableCounts: Record<string, number>;
  dbPath: string;
}

export interface ClearCacheResult {
  clearedKeys: number;
}

export function fetchDbInfo(): Promise<DbInfo> {
  return apiRequest<DbInfo>("/v1/system/db-info");
}

export function clearCache(): Promise<ClearCacheResult> {
  return apiRequest<ClearCacheResult>("/v1/system/clear-cache", { method: "POST" });
}
