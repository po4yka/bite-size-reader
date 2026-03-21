import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createRule,
  deleteRule,
  fetchRuleLogs,
  fetchRules,
  testRule,
  updateRule,
} from "../api/rules";
import type { CreateRulePayload, UpdateRulePayload } from "../api/rules";
import { queryKeys } from "../api/queryKeys";

export function useRules() {
  return useQuery({
    queryKey: queryKeys.rules.list(),
    queryFn: fetchRules,
  });
}

export function useCreateRule() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: CreateRulePayload) => createRule(data),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.rules.all });
    },
  });
}

export function useUpdateRule() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: UpdateRulePayload }) => updateRule(id, data),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.rules.all });
    },
  });
}

export function useDeleteRule() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => deleteRule(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.rules.all });
    },
  });
}

export function useTestRule() {
  return useMutation({
    mutationFn: ({ id, summaryId }: { id: number; summaryId: number }) => testRule(id, summaryId),
  });
}

export function useRuleLogs(id: number | null) {
  return useQuery({
    queryKey: queryKeys.rules.logs(id ?? 0),
    queryFn: () => fetchRuleLogs(id ?? 0),
    enabled: id != null,
  });
}
