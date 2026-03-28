import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createBackup,
  deleteBackup,
  fetchBackup,
  fetchBackups,
  fetchSchedule,
  restoreBackup,
  updateSchedule,
} from "../api/backups";
import type { BackupSchedule } from "../api/backups";
import { queryKeys } from "../api/queryKeys";

export function useBackups() {
  return useQuery({
    queryKey: queryKeys.backups.list(),
    queryFn: fetchBackups,
  });
}

export function useBackup(id: number | null) {
  return useQuery({
    queryKey: queryKeys.backups.detail(id ?? 0),
    queryFn: () => fetchBackup(id ?? 0),
    enabled: id != null,
  });
}

export function useBackupPolling(id: number | null, isProcessing: boolean) {
  return useQuery({
    queryKey: queryKeys.backups.detail(id ?? 0),
    queryFn: () => fetchBackup(id ?? 0),
    enabled: id != null && isProcessing,
    refetchInterval: isProcessing ? 2000 : false,
  });
}

export function useCreateBackup() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => createBackup(),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.backups.all });
    },
  });
}

export function useDeleteBackup() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => deleteBackup(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.backups.all });
    },
  });
}

export function useRestoreBackup() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => restoreBackup(file),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.backups.all });
    },
  });
}

export function useBackupSchedule() {
  return useQuery({
    queryKey: queryKeys.backups.schedule(),
    queryFn: fetchSchedule,
  });
}

export function useUpdateSchedule() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: Partial<BackupSchedule>) => updateSchedule(data),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.backups.all });
    },
  });
}
