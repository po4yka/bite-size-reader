import { apiRequest } from "./client";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type BackupType = "manual" | "scheduled";
export type BackupStatus = "pending" | "processing" | "completed" | "failed";

export interface Backup {
  id: number;
  type: BackupType;
  status: BackupStatus;
  filePath: string | null;
  fileSizeBytes: number | null;
  itemsCount: number | null;
  error: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface BackupSchedule {
  backupEnabled: boolean | null;
  backupFrequency: string | null;
  backupRetentionCount: number | null;
}

export interface RestoreResult {
  restored: Record<string, number>;
  skipped: Record<string, number>;
  errors: string[];
}

// ---------------------------------------------------------------------------
// API functions
// ---------------------------------------------------------------------------

export async function fetchBackups(): Promise<Backup[]> {
  const data = await apiRequest<{ backups: Backup[] }>("/v1/backups");
  return data.backups;
}

export async function createBackup(): Promise<Backup> {
  return apiRequest<Backup>("/v1/backups", {
    method: "POST",
  });
}

export async function fetchBackup(id: number): Promise<Backup> {
  return apiRequest<Backup>(`/v1/backups/${id}`);
}

export async function deleteBackup(id: number): Promise<{ deleted: boolean; id: number }> {
  return apiRequest<{ deleted: boolean; id: number }>(`/v1/backups/${id}`, {
    method: "DELETE",
  });
}

export function getBackupDownloadUrl(id: number): string {
  return `/v1/backups/${id}/download`;
}

export async function restoreBackup(file: File): Promise<RestoreResult> {
  const formData = new FormData();
  formData.append("file", file);
  return apiRequest<RestoreResult>("/v1/backups/restore", {
    method: "POST",
    body: formData,
  });
}

export async function fetchSchedule(): Promise<BackupSchedule> {
  const data = await apiRequest<{ schedule: BackupSchedule }>("/v1/backups/schedule");
  return data.schedule;
}

export async function updateSchedule(
  data: Partial<BackupSchedule>,
): Promise<BackupSchedule> {
  const payload: Record<string, unknown> = {};
  if (data.backupEnabled !== undefined) payload.backup_enabled = data.backupEnabled;
  if (data.backupFrequency !== undefined) payload.backup_frequency = data.backupFrequency;
  if (data.backupRetentionCount !== undefined) payload.backup_retention_count = data.backupRetentionCount;

  const result = await apiRequest<{ schedule: BackupSchedule }>("/v1/backups/schedule", {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
  return result.schedule;
}
