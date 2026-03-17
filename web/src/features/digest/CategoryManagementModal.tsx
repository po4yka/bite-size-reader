import { useState } from "react";
import {
  Button,
  ComposedModal,
  InlineNotification,
  ModalBody,
  ModalFooter,
  ModalHeader,
  TextInput,
} from "@carbon/react";
import type { DigestCategory } from "../../api/digest";
import { useCreateCategory, useDeleteCategory, useUpdateCategory } from "../../hooks/useDigest";

export function CategoryManagementModal({
  open,
  onClose,
  categories,
}: {
  open: boolean;
  onClose: () => void;
  categories: DigestCategory[];
}) {
  const [newCategoryName, setNewCategoryName] = useState("");
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editingName, setEditingName] = useState("");

  const createMutation = useCreateCategory();
  const updateMutation = useUpdateCategory();
  const deleteMutation = useDeleteCategory();

  return (
    <ComposedModal open={open} onClose={onClose}>
      <ModalHeader title="Manage Categories" />
      <ModalBody>
        <div className="form-actions" style={{ marginBottom: "1rem" }}>
          <TextInput
            id="new-category-input"
            labelText="New category"
            placeholder="Category name"
            value={newCategoryName}
            onChange={(e) => setNewCategoryName(e.currentTarget.value)}
          />
          <Button
            kind="secondary"
            size="sm"
            disabled={!newCategoryName.trim() || createMutation.isPending}
            onClick={() => createMutation.mutate(newCategoryName.trim(), { onSuccess: () => setNewCategoryName("") })}
          >
            Add
          </Button>
        </div>

        {(createMutation.error || updateMutation.error || deleteMutation.error) && (
          <InlineNotification
            kind="error"
            title="Category operation failed"
            subtitle={
              ((createMutation.error || updateMutation.error || deleteMutation.error) as Error | null)?.message ??
              "Unknown error"
            }
            hideCloseButton
          />
        )}

        {categories.length === 0 && <p className="muted">No categories yet.</p>}

        <ul className="digest-list">
          {categories.map((cat) => (
            <li
              key={cat.id}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "0.5rem",
                padding: "0.5rem 0",
                borderBottom: "1px solid var(--cds-border-subtle)",
              }}
            >
              {editingId === cat.id ? (
                <>
                  <TextInput
                    id={`edit-cat-${cat.id}`}
                    labelText=""
                    hideLabel
                    value={editingName}
                    onChange={(e) => setEditingName(e.currentTarget.value)}
                    size="sm"
                  />
                  <Button
                    kind="primary"
                    size="sm"
                    disabled={!editingName.trim() || updateMutation.isPending}
                    onClick={() => updateMutation.mutate({ id: cat.id, name: editingName.trim() }, { onSuccess: () => { setEditingId(null); setEditingName(""); } })}
                  >
                    Save
                  </Button>
                  <Button kind="ghost" size="sm" onClick={() => setEditingId(null)}>
                    Cancel
                  </Button>
                </>
              ) : (
                <>
                  <span style={{ flex: 1 }}>{cat.name}</span>
                  <Button
                    kind="ghost"
                    size="sm"
                    onClick={() => {
                      setEditingId(cat.id);
                      setEditingName(cat.name);
                    }}
                  >
                    Edit
                  </Button>
                  <Button
                    kind="danger--ghost"
                    size="sm"
                    disabled={deleteMutation.isPending}
                    onClick={() => deleteMutation.mutate(cat.id)}
                  >
                    Delete
                  </Button>
                </>
              )}
            </li>
          ))}
        </ul>
      </ModalBody>
      <ModalFooter>
        <Button kind="secondary" onClick={onClose}>
          Close
        </Button>
      </ModalFooter>
    </ComposedModal>
  );
}
