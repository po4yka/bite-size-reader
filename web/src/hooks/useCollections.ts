import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  addSummaryToCollection,
  createCollection,
  deleteCollection,
  fetchCollectionItems,
  fetchCollectionTree,
  moveCollectionItems,
  removeSummaryFromCollection,
  reorderCollectionItems,
  updateCollection,
} from "../api/collections";
import { queryKeys } from "../api/queryKeys";

export function useCollectionTree() {
  return useQuery({
    queryKey: queryKeys.collections.tree,
    queryFn: fetchCollectionTree,
  });
}

export function useCollectionItems(collectionId: number | null) {
  return useQuery({
    queryKey: queryKeys.collections.items(collectionId ?? 0),
    queryFn: () => fetchCollectionItems(collectionId ?? 0),
    enabled: Boolean(collectionId),
  });
}

export function useCreateCollection() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ name, parentId }: { name: string; parentId?: number }) =>
      createCollection(name, parentId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.collections.tree });
    },
  });
}

export function useRenameCollection() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ collectionId, name }: { collectionId: number; name: string }) =>
      updateCollection(collectionId, { name }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.collections.tree });
    },
  });
}

export function useDeleteCollection() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (collectionId: number) => deleteCollection(collectionId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.collections.tree });
      void queryClient.invalidateQueries({ queryKey: ["collections", "items"] });
    },
  });
}

export function useRemoveFromCollection() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ collectionId, summaryId }: { collectionId: number; summaryId: number }) =>
      removeSummaryFromCollection(collectionId, summaryId),
    onSuccess: (_data, { collectionId }) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.collections.items(collectionId) });
      void queryClient.invalidateQueries({ queryKey: queryKeys.collections.tree });
    },
  });
}

export function useMoveCollectionItems() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      fromCollectionId,
      summaryIds,
      toCollectionId,
    }: {
      fromCollectionId: number;
      summaryIds: number[];
      toCollectionId: number;
    }) => moveCollectionItems(fromCollectionId, summaryIds, toCollectionId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["collections", "items"] });
      void queryClient.invalidateQueries({ queryKey: queryKeys.collections.tree });
    },
  });
}

export function useReorderCollectionItems(collectionId: number | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (items: Array<{ summary_id: number; position: number }>) => {
      if (!collectionId) throw new Error("Select a collection first.");
      return reorderCollectionItems(collectionId, items);
    },
    onSuccess: () => {
      if (collectionId != null) {
        void queryClient.invalidateQueries({ queryKey: queryKeys.collections.items(collectionId) });
      }
    },
  });
}

export function useAddToCollection() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ collectionId, summaryId }: { collectionId: number; summaryId: number }) =>
      addSummaryToCollection(collectionId, summaryId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.collections.tree });
      void queryClient.invalidateQueries({ queryKey: ["collections", "items"] });
    },
  });
}
