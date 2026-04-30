import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { queryKeys } from "../api/queryKeys";
import {
  fetchSignalHealth,
  fetchSignalSourceHealth,
  fetchSignals,
  setSignalSourceActive,
  updateSignalFeedback,
  upsertSignalTopic,
  type SignalFeedbackAction,
} from "../api/signals";

export function useSignals() {
  return useQuery({
    queryKey: queryKeys.signals.list(),
    queryFn: fetchSignals,
  });
}

export function useSignalHealth() {
  return useQuery({
    queryKey: queryKeys.signals.health,
    queryFn: fetchSignalHealth,
  });
}

export function useSignalSourceHealth() {
  return useQuery({
    queryKey: queryKeys.signals.sources,
    queryFn: fetchSignalSourceHealth,
  });
}

export function useSignalFeedback() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ signalId, action }: { signalId: number; action: SignalFeedbackAction }) =>
      updateSignalFeedback(signalId, action),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.signals.all });
    },
  });
}

export function useSetSignalSourceActive() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ sourceId, isActive }: { sourceId: number; isActive: boolean }) =>
      setSignalSourceActive(sourceId, isActive),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.signals.all });
    },
  });
}

export function useUpsertSignalTopic() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: upsertSignalTopic,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.signals.all });
    },
  });
}
