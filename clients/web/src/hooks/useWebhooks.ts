import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createWebhook,
  deleteWebhook,
  fetchDeliveries,
  fetchWebhooks,
  rotateSecret,
  testWebhook,
  updateWebhook,
} from "../api/webhooks";
import type { CreateWebhookPayload, UpdateWebhookPayload } from "../api/webhooks";
import { queryKeys } from "../api/queryKeys";

export function useWebhooks() {
  return useQuery({
    queryKey: queryKeys.webhooks.list(),
    queryFn: fetchWebhooks,
  });
}

export function useCreateWebhook() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: CreateWebhookPayload) => createWebhook(data),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.webhooks.all });
    },
  });
}

export function useUpdateWebhook() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: UpdateWebhookPayload }) => updateWebhook(id, data),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.webhooks.all });
    },
  });
}

export function useDeleteWebhook() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => deleteWebhook(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.webhooks.all });
    },
  });
}

export function useTestWebhook() {
  return useMutation({
    mutationFn: (id: number) => testWebhook(id),
  });
}

export function useDeliveries(id: number | null) {
  return useQuery({
    queryKey: queryKeys.webhooks.deliveries(id ?? 0),
    queryFn: () => fetchDeliveries(id ?? 0),
    enabled: id != null,
  });
}

export function useRotateSecret() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => rotateSecret(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.webhooks.all });
    },
  });
}
