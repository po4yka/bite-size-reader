import { useState } from "react";
import {
  BracketButton,
  BrutalistModal,
  MonoInput,
  StatusBadge,
} from "../../design";
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
    <BrutalistModal open={open} onClose={onClose} modalHeading="Manage Categories" passiveModal>
      <div className="form-actions" style={{ marginBottom: "1rem" }}>
        <MonoInput
          id="new-category-input"
          labelText="New category"
          placeholder="Category name"
          value={newCategoryName}
          onChange={(e) => setNewCategoryName(e.currentTarget.value)}
        />
        <BracketButton
          kind="secondary"
          size="sm"
          disabled={!newCategoryName.trim() || createMutation.isPending}
          onClick={() => createMutation.mutate(newCategoryName.trim(), { onSuccess: () => setNewCategoryName("") })}
        >
          Add
        </BracketButton>
      </div>

      {(createMutation.error || updateMutation.error || deleteMutation.error) && (
        <StatusBadge severity="alarm" title="Category operation failed">
          {((createMutation.error || updateMutation.error || deleteMutation.error) as Error | null)?.message ??
            "Unknown error"}
        </StatusBadge>
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
              borderBottom: "1px solid var(--rtk-color-border-subtle)",
            }}
          >
            {editingId === cat.id ? (
              <>
                <MonoInput
                  id={`edit-cat-${cat.id}`}
                  labelText=""
                  hideLabel
                  value={editingName}
                  onChange={(e) => setEditingName(e.currentTarget.value)}
                  size="sm"
                />
                <BracketButton
                  kind="primary"
                  size="sm"
                  disabled={!editingName.trim() || updateMutation.isPending}
                  onClick={() => updateMutation.mutate({ id: cat.id, name: editingName.trim() }, { onSuccess: () => { setEditingId(null); setEditingName(""); } })}
                >
                  Save
                </BracketButton>
                <BracketButton kind="ghost" size="sm" onClick={() => setEditingId(null)}>
                  Cancel
                </BracketButton>
              </>
            ) : (
              <>
                <span style={{ flex: 1 }}>{cat.name}</span>
                <BracketButton
                  kind="ghost"
                  size="sm"
                  onClick={() => {
                    setEditingId(cat.id);
                    setEditingName(cat.name);
                  }}
                >
                  Edit
                </BracketButton>
                <BracketButton
                  kind="danger--ghost"
                  size="sm"
                  disabled={deleteMutation.isPending}
                  onClick={() => deleteMutation.mutate(cat.id)}
                >
                  Delete
                </BracketButton>
              </>
            )}
          </li>
        ))}
      </ul>

      <div style={{ marginTop: "1rem", display: "flex", justifyContent: "flex-end" }}>
        <BracketButton kind="secondary" onClick={onClose}>
          Close
        </BracketButton>
      </div>
    </BrutalistModal>
  );
}
