import { useMemo, useState } from "react";
import {
  Button,
  Checkbox,
  DataTable,
  DataTableSkeleton,
  InlineNotification,
  Modal,
  Select,
  SelectItem,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableHeader,
  TableRow,
  TextInput,
} from "@carbon/react";
import { QueryErrorNotification } from "../../components/QueryErrorNotification";
import {
  useTags,
  useCreateTag,
  useUpdateTag,
  useDeleteTag,
  useMergeTags,
} from "../../hooks/useTags";

export default function TagManagementPage() {
  const [newTagName, setNewTagName] = useState("");
  const [newTagColor, setNewTagColor] = useState("");
  const [editingTagId, setEditingTagId] = useState<number | null>(null);
  const [editName, setEditName] = useState("");
  const [editColor, setEditColor] = useState("");
  const [deleteTagId, setDeleteTagId] = useState<number | null>(null);
  const [mergeOpen, setMergeOpen] = useState(false);
  const [mergeSourceIds, setMergeSourceIds] = useState<Set<number>>(new Set());
  const [mergeTargetId, setMergeTargetId] = useState("");

  const tagsQuery = useTags();
  const createMutation = useCreateTag();
  const updateMutation = useUpdateTag();
  const deleteMutation = useDeleteTag();
  const mergeMutation = useMergeTags();

  const tags = useMemo(() => tagsQuery.data ?? [], [tagsQuery.data]);

  const deleteTagObj = useMemo(
    () => tags.find((t) => t.id === deleteTagId) ?? null,
    [tags, deleteTagId],
  );

  const headers = [
    { key: "name", header: "Name" },
    { key: "color", header: "Color" },
    { key: "summaryCount", header: "Summaries" },
    { key: "createdAt", header: "Created" },
    { key: "actions", header: "Actions" },
  ];

  const rows = useMemo(() => {
    return tags.map((tag) => ({
      id: String(tag.id),
      name: tag.name,
      color: tag.color ?? "",
      summaryCount: String(tag.summaryCount),
      createdAt: tag.createdAt ? new Date(tag.createdAt).toLocaleDateString() : "",
      actions: tag.id,
    }));
  }, [tags]);

  const firstMutationError = [
    createMutation.error,
    updateMutation.error,
    deleteMutation.error,
    mergeMutation.error,
  ].find((error): error is Error => error instanceof Error);

  function handleCreate(): void {
    const name = newTagName.trim();
    if (!name) return;
    createMutation.mutate(
      { name, color: newTagColor.trim() || undefined },
      {
        onSuccess: () => {
          setNewTagName("");
          setNewTagColor("");
        },
      },
    );
  }

  function handleStartEdit(tagId: number): void {
    const tag = tags.find((t) => t.id === tagId);
    if (!tag) return;
    setEditingTagId(tagId);
    setEditName(tag.name);
    setEditColor(tag.color ?? "");
  }

  function handleSaveEdit(): void {
    if (editingTagId == null) return;
    updateMutation.mutate(
      {
        tagId: editingTagId,
        payload: {
          name: editName.trim() || undefined,
          color: editColor.trim() || null,
        },
      },
      { onSuccess: () => setEditingTagId(null) },
    );
  }

  function handleToggleMergeSource(tagId: number): void {
    setMergeSourceIds((prev) => {
      const next = new Set(prev);
      if (next.has(tagId)) {
        next.delete(tagId);
      } else {
        next.add(tagId);
      }
      return next;
    });
  }

  function handleMergeSubmit(): void {
    const targetId = Number(mergeTargetId);
    if (!targetId || mergeSourceIds.size === 0) return;
    mergeMutation.mutate(
      { sourceTagIds: Array.from(mergeSourceIds), targetTagId: targetId },
      {
        onSuccess: () => {
          setMergeOpen(false);
          setMergeSourceIds(new Set());
          setMergeTargetId("");
        },
      },
    );
  }

  const mergeTargetOptions = useMemo(
    () => tags.filter((t) => !mergeSourceIds.has(t.id)),
    [tags, mergeSourceIds],
  );

  const canCreate = newTagName.trim().length > 0 && !createMutation.isPending;
  const canMerge = mergeSourceIds.size > 0 && Boolean(mergeTargetId) && !mergeMutation.isPending;

  return (
    <section className="page-section">
      <h1>Tags</h1>

      <div className="form-actions">
        <TextInput
          id="new-tag-name"
          labelText="Tag name"
          value={newTagName}
          onChange={(e) => setNewTagName(e.currentTarget.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && canCreate) handleCreate();
          }}
        />
        <TextInput
          id="new-tag-color"
          labelText="Color (optional hex)"
          value={newTagColor}
          onChange={(e) => setNewTagColor(e.currentTarget.value)}
          placeholder="#3b82f6"
        />
        <Button kind="secondary" onClick={handleCreate} disabled={!canCreate}>
          Create tag
        </Button>
        <Button kind="tertiary" onClick={() => setMergeOpen(true)} disabled={tags.length < 2}>
          Merge tags
        </Button>
      </div>

      {firstMutationError && (
        <InlineNotification
          kind="error"
          title="Tag action failed"
          subtitle={firstMutationError.message}
          hideCloseButton
        />
      )}

      {tagsQuery.isLoading && (
        <DataTableSkeleton columnCount={headers.length} rowCount={6} showToolbar={false} />
      )}
      <QueryErrorNotification error={tagsQuery.error} title="Failed to load tags" />

      {!tagsQuery.isLoading && (
        <DataTable rows={rows} headers={headers}>
          {({ rows, headers, getHeaderProps, getRowProps, getTableProps }) => (
            <TableContainer title="Tags">
              <Table {...getTableProps()}>
                <TableHead>
                  <TableRow>
                    {headers.map((header) => (
                      <TableHeader {...getHeaderProps({ header })}>
                        {header.header}
                      </TableHeader>
                    ))}
                  </TableRow>
                </TableHead>
                <TableBody>
                  {rows.map((row) => {
                    const tagId = row.cells.find((c) => c.info.header === "actions")?.value as number;
                    const isEditing = editingTagId === tagId;
                    return (
                      <TableRow {...getRowProps({ row })}>
                        {row.cells.map((cell) => {
                          if (cell.info.header === "name" && isEditing) {
                            return (
                              <TableCell key={cell.id}>
                                <TextInput
                                  id={`edit-name-${tagId}`}
                                  labelText=""
                                  hideLabel
                                  value={editName}
                                  onChange={(e) => setEditName(e.currentTarget.value)}
                                  size="sm"
                                />
                              </TableCell>
                            );
                          }
                          if (cell.info.header === "color") {
                            const colorValue = cell.value as string;
                            if (isEditing) {
                              return (
                                <TableCell key={cell.id}>
                                  <TextInput
                                    id={`edit-color-${tagId}`}
                                    labelText=""
                                    hideLabel
                                    value={editColor}
                                    onChange={(e) => setEditColor(e.currentTarget.value)}
                                    size="sm"
                                    placeholder="#hex"
                                  />
                                </TableCell>
                              );
                            }
                            return (
                              <TableCell key={cell.id}>
                                {colorValue ? (
                                  <span style={{ display: "inline-flex", alignItems: "center", gap: "0.5rem" }}>
                                    <span
                                      style={{
                                        display: "inline-block",
                                        width: "1rem",
                                        height: "1rem",
                                        borderRadius: "50%",
                                        backgroundColor: colorValue,
                                      }}
                                    />
                                    {colorValue}
                                  </span>
                                ) : (
                                  "--"
                                )}
                              </TableCell>
                            );
                          }
                          if (cell.info.header === "actions") {
                            return (
                              <TableCell key={cell.id}>
                                <div className="table-actions">
                                  {isEditing ? (
                                    <>
                                      <Button
                                        kind="secondary"
                                        size="sm"
                                        onClick={handleSaveEdit}
                                        disabled={updateMutation.isPending}
                                      >
                                        Save
                                      </Button>
                                      <Button
                                        kind="ghost"
                                        size="sm"
                                        onClick={() => setEditingTagId(null)}
                                      >
                                        Cancel
                                      </Button>
                                    </>
                                  ) : (
                                    <>
                                      <Button
                                        kind="ghost"
                                        size="sm"
                                        onClick={() => handleStartEdit(tagId)}
                                      >
                                        Edit
                                      </Button>
                                      <Button
                                        kind="danger--ghost"
                                        size="sm"
                                        onClick={() => setDeleteTagId(tagId)}
                                        disabled={deleteMutation.isPending}
                                      >
                                        Delete
                                      </Button>
                                    </>
                                  )}
                                </div>
                              </TableCell>
                            );
                          }
                          return <TableCell key={cell.id}>{cell.value as string}</TableCell>;
                        })}
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </TableContainer>
          )}
        </DataTable>
      )}

      <Modal
        open={deleteTagId != null}
        modalHeading="Delete tag"
        primaryButtonText={deleteMutation.isPending ? "Deleting..." : "Delete"}
        secondaryButtonText="Cancel"
        danger
        onRequestClose={() => {
          if (!deleteMutation.isPending) setDeleteTagId(null);
        }}
        onRequestSubmit={() => {
          if (deleteTagId != null) {
            deleteMutation.mutate(deleteTagId, {
              onSuccess: () => setDeleteTagId(null),
            });
          }
        }}
      >
        <p>
          {deleteTagObj
            ? `Delete tag "${deleteTagObj.name}"? Summaries will keep their other tags.`
            : "Delete this tag?"}
        </p>
      </Modal>

      <Modal
        open={mergeOpen}
        modalHeading="Merge tags"
        primaryButtonText={mergeMutation.isPending ? "Merging..." : "Merge"}
        secondaryButtonText="Cancel"
        primaryButtonDisabled={!canMerge}
        onRequestClose={() => {
          if (!mergeMutation.isPending) {
            setMergeOpen(false);
            setMergeSourceIds(new Set());
            setMergeTargetId("");
          }
        }}
        onRequestSubmit={handleMergeSubmit}
      >
        <p style={{ marginBottom: "1rem" }}>
          Select source tags to merge into a target tag. Source tags will be deleted
          and their summaries reassigned.
        </p>
        <div style={{ marginBottom: "1rem" }}>
          <p style={{ fontWeight: 600, marginBottom: "0.5rem" }}>Source tags (select one or more):</p>
          {tags.map((tag) => (
            <Checkbox
              key={tag.id}
              id={`merge-source-${tag.id}`}
              labelText={`${tag.name} (${tag.summaryCount})`}
              checked={mergeSourceIds.has(tag.id)}
              onChange={() => handleToggleMergeSource(tag.id)}
            />
          ))}
        </div>
        <Select
          id="merge-target"
          labelText="Target tag"
          value={mergeTargetId}
          onChange={(e) => setMergeTargetId(e.currentTarget.value)}
          disabled={mergeTargetOptions.length === 0}
        >
          <SelectItem value="" text="Choose target..." />
          {mergeTargetOptions.map((tag) => (
            <SelectItem key={tag.id} value={String(tag.id)} text={tag.name} />
          ))}
        </Select>
      </Modal>
    </section>
  );
}
