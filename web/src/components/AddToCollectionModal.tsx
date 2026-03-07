import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  InlineLoading,
  InlineNotification,
  Modal,
  Select,
  SelectItem,
  TextInput,
} from "@carbon/react";
import {
  addSummaryToCollection,
  createCollection,
  fetchCollectionTree,
} from "../api/collections";
import type { Collection } from "../api/types";

interface AddToCollectionModalProps {
  open: boolean;
  summaryId: number | null;
  onClose: () => void;
}

function flattenCollections(input: Collection[]): Collection[] {
  const result: Collection[] = [];

  function walk(items: Collection[], prefix: string): void {
    for (const item of items) {
      result.push({
        ...item,
        name: prefix ? `${prefix} / ${item.name}` : item.name,
      });
      walk(item.children ?? [], prefix ? `${prefix} / ${item.name}` : item.name);
    }
  }

  walk(input, "");
  return result;
}

export default function AddToCollectionModal({ open, summaryId, onClose }: AddToCollectionModalProps) {
  const queryClient = useQueryClient();
  const [selectedCollectionId, setSelectedCollectionId] = useState<string>("");
  const [newCollectionName, setNewCollectionName] = useState("");

  const collectionsQuery = useQuery({
    queryKey: ["collections-tree"],
    queryFn: fetchCollectionTree,
    enabled: open,
  });

  const options = useMemo(() => flattenCollections(collectionsQuery.data ?? []), [collectionsQuery.data]);

  useEffect(() => {
    if (!open) return;
    setNewCollectionName("");
    if (options.length > 0) {
      setSelectedCollectionId(String(options[0]?.id ?? ""));
    } else {
      setSelectedCollectionId("");
    }
  }, [open, options]);

  const addMutation = useMutation({
    mutationFn: async () => {
      if (!summaryId) {
        throw new Error("No summary selected.");
      }

      let targetCollectionId = Number(selectedCollectionId) || null;

      if (newCollectionName.trim()) {
        const created = await createCollection(newCollectionName.trim());
        targetCollectionId = created.id;
      }

      if (!targetCollectionId) {
        throw new Error("Select a collection or create a new one.");
      }

      await addSummaryToCollection(targetCollectionId, summaryId);
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["collections-tree"] });
      void queryClient.invalidateQueries({ queryKey: ["collection-items"] });
      onClose();
    },
  });

  const canSubmit = Boolean(summaryId) && (Boolean(selectedCollectionId) || newCollectionName.trim().length > 0);

  return (
    <Modal
      open={open}
      modalHeading="Add to collection"
      primaryButtonText={addMutation.isPending ? "Adding..." : "Add"}
      secondaryButtonText="Cancel"
      primaryButtonDisabled={!canSubmit || addMutation.isPending}
      onRequestClose={() => {
        if (!addMutation.isPending) {
          onClose();
        }
      }}
      onRequestSubmit={() => {
        addMutation.mutate();
      }}
    >
      {collectionsQuery.isLoading && <InlineLoading description="Loading collections..." />}

      {collectionsQuery.error && (
        <InlineNotification
          kind="error"
          title="Failed to load collections"
          subtitle={collectionsQuery.error instanceof Error ? collectionsQuery.error.message : "Unknown error"}
          hideCloseButton
        />
      )}

      {addMutation.error && (
        <InlineNotification
          kind="error"
          title="Failed to add summary"
          subtitle={addMutation.error instanceof Error ? addMutation.error.message : "Unknown error"}
          hideCloseButton
        />
      )}

      <div className="digest-form-grid">
        <Select
          id="collection-target"
          labelText="Existing collection"
          value={selectedCollectionId}
          onChange={(event) => setSelectedCollectionId(event.currentTarget.value)}
          disabled={options.length === 0}
        >
          {options.length === 0 ? (
            <SelectItem value="" text="No collections yet" />
          ) : (
            options.map((item) => (
              <SelectItem key={item.id} value={String(item.id)} text={item.name} />
            ))
          )}
        </Select>

        <TextInput
          id="new-collection-inline"
          labelText="Or create new collection"
          value={newCollectionName}
          onChange={(event) => setNewCollectionName(event.currentTarget.value)}
          placeholder="Collection name"
        />
      </div>
    </Modal>
  );
}
