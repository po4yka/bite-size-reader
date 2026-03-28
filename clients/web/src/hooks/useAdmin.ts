import { useMutation, useQuery } from "@tanstack/react-query";
import {
  clearCache,
  fetchAdminJobs,
  fetchAdminUsers,
  fetchAuditLog,
  fetchContentHealth,
  fetchDbInfo,
  fetchMetrics,
} from "../api/admin";
import type { AuditLogParams } from "../api/admin";
import { queryKeys } from "../api/queryKeys";

export function useDbInfo() {
  return useQuery({
    queryKey: queryKeys.admin.dbInfo,
    queryFn: fetchDbInfo,
  });
}

export function useClearCache(onSuccess?: (result: { clearedKeys: number }) => void, onError?: (err: Error) => void) {
  return useMutation({
    mutationFn: clearCache,
    onSuccess,
    onError,
  });
}

export function useAdminUsers() {
  return useQuery({
    queryKey: queryKeys.admin.users,
    queryFn: fetchAdminUsers,
  });
}

export function useAdminJobs() {
  return useQuery({
    queryKey: queryKeys.admin.jobs,
    queryFn: fetchAdminJobs,
    refetchInterval: 15_000,
  });
}

export function useContentHealth() {
  return useQuery({
    queryKey: queryKeys.admin.health,
    queryFn: fetchContentHealth,
  });
}

export function useMetrics() {
  return useQuery({
    queryKey: queryKeys.admin.metrics,
    queryFn: fetchMetrics,
  });
}

export function useAuditLog(params: AuditLogParams = {}) {
  return useQuery({
    queryKey: queryKeys.admin.auditLog(params as Record<string, unknown>),
    queryFn: () => fetchAuditLog(params),
  });
}
