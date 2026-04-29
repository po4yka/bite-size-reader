import { useEffect, useMemo, useState } from "react";
import {
  InlineLoading,
  Modal,
  Select,
  SelectItem,
  TextInput,
} from "../design";
import { createCollection } from "../api/collections";
import { flattenCollections } from "../lib/collections";
import { useCollectionTree, useAddToCollection } from "../hooks/useCollections";
import { QueryErrorNotification } from "./QueryErrorNotification";

interface AddToCollectionModalProps {
  open: boolean;
  summaryId: number | null;
  onClose: () => void;
}


export default function AddToCollectionModal({ open, summaryId, onClose }: AddToCollectionModalProps) {
  const [selectedCollectionId, setSelectedCollectionId] = useState<string>("");
  const [newCollectionName, setNewCollectionName] = useState("");

  const collectionsQuery = useCollectionTree();
  const addMutation = useAddToCollection();

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

  async function handleSubmit(): Promise<void> {
    if (!summaryId) return;

    let targetCollectionId = Number(selectedCollectionId) || null;
    if (newCollectionName.trim()) {
      const created = await createCollection(newCollectionName.trim());
      targetCollectionId = created.id;
    }
    if (!targetCollectionId) return;

    addMutation.mutate({ collectionId: targetCollectionId, summaryId }, { onSuccess: () => onClose() });
  }

  const canSubmit = Boolean(summaryId) && (Boolean(selectedCollectionId) || newCollectionName.trim().length > 0);

  return (
    <Modal
      open={open}
      modalHeading="Add to collection"
      primaryButtonText={addMutation.isPending ? "Adding…" : "Add"}
      secondaryButtonText="Cancel"
      primaryButtonDisabled={!canSubmit || addMutation.isPending}
      onRequestClose={() => {
        if (!addMutation.isPending) {
          onClose();
        }
      }}
      onRequestSubmit={() => {
        void handleSubmit();
      }}
    >
      {collectionsQuery.isLoading && <InlineLoading description="Loading collections…" />}

      <QueryErrorNotification error={collectionsQuery.error} title="Failed to load collections" />
      <QueryErrorNotification error={addMutation.error} title="Failed to add summary" />

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
          placeholder="Collection name…"
        />
      </div>
    </Modal>
  );
}
