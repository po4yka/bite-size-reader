import { Fragment, useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Button,
  DataTable,
  InlineLoading,
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
  TreeNode,
  TreeView,
} from "@carbon/react";
import {
  createCollection,
  deleteCollection,
  fetchCollectionItems,
  fetchCollectionTree,
  moveCollectionItems,
  removeSummaryFromCollection,
  reorderCollectionItems,
  updateCollection,
} from "../../api/collections";
import type { Collection, CollectionItem } from "../../api/types";

function RenderTree({
  collection,
  onSelect,
}: {
  collection: Collection;
  onSelect: (id: number) => void;
}) {
  return (
    <TreeNode
      id={String(collection.id)}
      label={`${collection.name} (${collection.itemCount})`}
      onSelect={() => onSelect(collection.id)}
    >
      {(collection.children ?? []).map((child) => (
        <RenderTree key={child.id} collection={child} onSelect={onSelect} />
      ))}
    </TreeNode>
  );
}

function flattenCollections(collections: Collection[]): Collection[] {
  const output: Collection[] = [];
  const visit = (items: Collection[]) => {
    for (const item of items) {
      output.push(item);
      visit(item.children ?? []);
    }
  };
  visit(collections);
  return output;
}

type ReorderDirection = -1 | 1;

function buildReorderPayload(
  items: CollectionItem[],
  summaryId: number,
  direction: ReorderDirection,
): Array<{ summary_id: number; position: number }> | null {
  const currentIndex = items.findIndex((item) => item.summaryId === summaryId);
  if (currentIndex < 0) return null;

  const targetIndex = currentIndex + direction;
  if (targetIndex < 0 || targetIndex >= items.length) return null;

  const reordered = [...items];
  const swap = reordered[currentIndex];
  reordered[currentIndex] = reordered[targetIndex];
  reordered[targetIndex] = swap;

  return reordered.map((item, index) => ({
    summary_id: item.summaryId,
    position: index + 1,
  }));
}

export default function CollectionsPage() {
  const navigate = useNavigate();
  const params = useParams();
  const queryClient = useQueryClient();

  const [selectedCollectionId, setSelectedCollectionId] = useState<number | null>(null);
  const [newCollectionName, setNewCollectionName] = useState("");
  const [createParentMode, setCreateParentMode] = useState<"root" | "selected">("selected");
  const [renameCollectionName, setRenameCollectionName] = useState("");
  const [deleteModalOpen, setDeleteModalOpen] = useState(false);
  const [moveSummaryId, setMoveSummaryId] = useState<number | null>(null);
  const [moveTargetCollectionId, setMoveTargetCollectionId] = useState("");
  const [moveNewCollectionName, setMoveNewCollectionName] = useState("");

  useEffect(() => {
    const fromRoute = Number(params.id);
    if (Number.isFinite(fromRoute) && fromRoute > 0) {
      setSelectedCollectionId(fromRoute);
    } else if (!params.id) {
      setSelectedCollectionId(null);
    }
  }, [params.id]);

  useEffect(() => {
    if (selectedCollectionId != null) return;
    setCreateParentMode("root");
  }, [selectedCollectionId]);

  const treeQuery = useQuery({
    queryKey: ["collections-tree"],
    queryFn: () => fetchCollectionTree(),
  });

  const itemsQuery = useQuery({
    queryKey: ["collection-items", selectedCollectionId],
    queryFn: () => fetchCollectionItems(selectedCollectionId ?? 0),
    enabled: Boolean(selectedCollectionId),
  });

  const flatCollections = useMemo(() => flattenCollections(treeQuery.data ?? []), [treeQuery.data]);

  const selectedCollection = useMemo(
    () => flatCollections.find((item) => item.id === selectedCollectionId) ?? null,
    [flatCollections, selectedCollectionId],
  );

  const sortedItems = useMemo(() => {
    return [...(itemsQuery.data ?? [])].sort((a, b) => {
      const positionA = a.position ?? Number.MAX_SAFE_INTEGER;
      const positionB = b.position ?? Number.MAX_SAFE_INTEGER;
      if (positionA !== positionB) {
        return positionA - positionB;
      }
      return a.summaryId - b.summaryId;
    });
  }, [itemsQuery.data]);

  const moveTargetOptions = useMemo(
    () => flatCollections.filter((collection) => collection.id !== selectedCollectionId),
    [flatCollections, selectedCollectionId],
  );

  useEffect(() => {
    setRenameCollectionName(selectedCollection?.name ?? "");
  }, [selectedCollection]);

  useEffect(() => {
    if (!treeQuery.isSuccess || selectedCollectionId == null) return;
    const exists = flatCollections.some((collection) => collection.id === selectedCollectionId);
    if (!exists) {
      setSelectedCollectionId(null);
      navigate("/collections", { replace: true });
    }
  }, [treeQuery.isSuccess, flatCollections, selectedCollectionId, navigate]);

  useEffect(() => {
    if (moveSummaryId == null) return;
    setMoveNewCollectionName("");
    setMoveTargetCollectionId(moveTargetOptions[0] ? String(moveTargetOptions[0].id) : "");
  }, [moveSummaryId, moveTargetOptions]);

  const createMutation = useMutation({
    mutationFn: ({ name, parentId }: { name: string; parentId?: number }) => createCollection(name, parentId),
    onSuccess: (collection) => {
      setNewCollectionName("");
      setSelectedCollectionId(collection.id);
      navigate(`/collections/${collection.id}`);
      void queryClient.invalidateQueries({ queryKey: ["collections-tree"] });
    },
  });

  const renameMutation = useMutation({
    mutationFn: ({ collectionId, name }: { collectionId: number; name: string }) =>
      updateCollection(collectionId, { name }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["collections-tree"] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (collectionId: number) => deleteCollection(collectionId),
    onSuccess: (_, collectionId) => {
      if (selectedCollectionId === collectionId) {
        setSelectedCollectionId(null);
        navigate("/collections");
      }
      setDeleteModalOpen(false);
      void queryClient.invalidateQueries({ queryKey: ["collections-tree"] });
      void queryClient.invalidateQueries({ queryKey: ["collection-items"] });
    },
  });

  const removeMutation = useMutation({
    mutationFn: ({ collectionId, summaryId }: { collectionId: number; summaryId: number }) =>
      removeSummaryFromCollection(collectionId, summaryId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["collection-items", selectedCollectionId] });
      void queryClient.invalidateQueries({ queryKey: ["collections-tree"] });
    },
  });

  const moveItemMutation = useMutation({
    mutationFn: async () => {
      if (!selectedCollectionId || !moveSummaryId) {
        throw new Error("Select an item to move.");
      }

      let targetCollectionId = Number(moveTargetCollectionId) || null;
      if (moveNewCollectionName.trim()) {
        const created = await createCollection(moveNewCollectionName.trim());
        targetCollectionId = created.id;
      }

      if (!targetCollectionId) {
        throw new Error("Select a target collection or create a new one.");
      }
      if (targetCollectionId === selectedCollectionId) {
        throw new Error("Choose a different target collection.");
      }

      await moveCollectionItems(selectedCollectionId, [moveSummaryId], targetCollectionId);
    },
    onSuccess: () => {
      setMoveSummaryId(null);
      setMoveNewCollectionName("");
      void queryClient.invalidateQueries({ queryKey: ["collection-items"] });
      void queryClient.invalidateQueries({ queryKey: ["collections-tree"] });
    },
  });

  const reorderMutation = useMutation({
    mutationFn: (items: Array<{ summary_id: number; position: number }>) => {
      if (!selectedCollectionId) {
        throw new Error("Select a collection first.");
      }
      return reorderCollectionItems(selectedCollectionId, items);
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["collection-items", selectedCollectionId] });
    },
  });

  const headers = [
    { key: "position", header: "Order" },
    { key: "title", header: "Title" },
    { key: "domain", header: "Domain" },
    { key: "createdAt", header: "Added" },
    { key: "actions", header: "Actions" },
  ];

  const rows = useMemo(() => {
    return sortedItems.map((item, index) => ({
      id: String(item.summaryId),
      position: String(index + 1),
      title: item.title ?? `Summary #${item.summaryId}`,
      domain: item.domain ?? "",
      createdAt: item.createdAt ? new Date(item.createdAt).toLocaleString() : "",
      actions: { summaryId: item.summaryId, index },
    }));
  }, [sortedItems]);

  const firstMutationError = [
    createMutation.error,
    renameMutation.error,
    deleteMutation.error,
    removeMutation.error,
    moveItemMutation.error,
    reorderMutation.error,
  ].find((error): error is Error => error instanceof Error);

  const canCreate = newCollectionName.trim().length > 0;
  const canRename = Boolean(selectedCollectionId) && renameCollectionName.trim().length > 0;

  const canMoveSubmit =
    moveSummaryId != null &&
    (Boolean(moveTargetCollectionId) || moveNewCollectionName.trim().length > 0) &&
    !moveItemMutation.isPending;

  function handleCollectionSelect(id: number): void {
    setSelectedCollectionId(id);
    navigate(`/collections/${id}`);
  }

  function handleMoveItem(summaryId: number): void {
    setMoveSummaryId(summaryId);
  }

  function handleReorder(summaryId: number, direction: ReorderDirection): void {
    const payload = buildReorderPayload(sortedItems, summaryId, direction);
    if (!payload) return;
    reorderMutation.mutate(payload);
  }

  return (
    <section className="page-section collections-layout">
      <div className="collections-tree">
        <h1>Collections</h1>

        <div className="form-actions">
          <TextInput
            id="new-collection"
            labelText="New collection"
            value={newCollectionName}
            onChange={(event) => setNewCollectionName(event.currentTarget.value)}
          />
          <Select
            id="new-collection-parent"
            labelText="Create location"
            value={createParentMode}
            onChange={(event) => setCreateParentMode(event.currentTarget.value as "root" | "selected")}
          >
            <SelectItem value="root" text="Top level" />
            <SelectItem
              value="selected"
              text={
                selectedCollection
                  ? `Inside ${selectedCollection.name}`
                  : "Inside selected collection (pick one first)"
              }
              disabled={!selectedCollection}
            />
          </Select>
          <Button
            kind="secondary"
            onClick={() =>
              createMutation.mutate({
                name: newCollectionName.trim(),
                parentId: createParentMode === "selected" ? selectedCollectionId ?? undefined : undefined,
              })
            }
            disabled={!canCreate || createMutation.isPending}
          >
            Create
          </Button>
        </div>

        {treeQuery.isLoading && <InlineLoading description="Loading collections..." />}
        {treeQuery.error && (
          <InlineNotification
            kind="error"
            title="Failed to load collections"
            subtitle={treeQuery.error instanceof Error ? treeQuery.error.message : "Unknown error"}
            hideCloseButton
          />
        )}

        {firstMutationError && (
          <InlineNotification
            kind="error"
            title="Collection action failed"
            subtitle={firstMutationError.message}
            hideCloseButton
          />
        )}

        {selectedCollection && (
          <div className="form-actions">
            <TextInput
              id="rename-collection"
              labelText="Rename selected collection"
              value={renameCollectionName}
              onChange={(event) => setRenameCollectionName(event.currentTarget.value)}
            />
            <Button
              kind="secondary"
              onClick={() =>
                selectedCollectionId &&
                renameMutation.mutate({
                  collectionId: selectedCollectionId,
                  name: renameCollectionName.trim(),
                })
              }
              disabled={!canRename || renameMutation.isPending}
            >
              Save name
            </Button>
            <Button
              kind="danger--ghost"
              onClick={() => setDeleteModalOpen(true)}
              disabled={deleteMutation.isPending}
            >
              Delete
            </Button>
          </div>
        )}

        <TreeView
          label="Collections"
          hideLabel
          active={selectedCollectionId != null ? String(selectedCollectionId) : undefined}
        >
          {(treeQuery.data ?? []).map((collection) => (
            <Fragment key={collection.id}>
              <RenderTree collection={collection} onSelect={handleCollectionSelect} />
            </Fragment>
          ))}
        </TreeView>
      </div>

      <div className="collections-items">
        <h2>{selectedCollection ? selectedCollection.name : "Select a collection"}</h2>

        {itemsQuery.isLoading && selectedCollectionId && <InlineLoading description="Loading collection items..." />}
        {itemsQuery.error && (
          <InlineNotification
            kind="error"
            title="Failed to load collection items"
            subtitle={itemsQuery.error instanceof Error ? itemsQuery.error.message : "Unknown error"}
            hideCloseButton
          />
        )}

        {selectedCollectionId && (
          <DataTable rows={rows} headers={headers}>
            {({ rows, headers, getHeaderProps, getRowProps, getTableProps }) => (
              <TableContainer title="Collection items">
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
                      const item = row.cells.find((cell) => cell.info.header === "Actions")?.value as {
                        summaryId: number;
                        index: number;
                      };
                      return (
                        <TableRow
                          {...getRowProps({ row })}
                          onClick={() => navigate(`/library/${item.summaryId}`)}
                          className="clickable-row"
                        >
                          {row.cells.map((cell) => {
                            if (cell.info.header === "Actions") {
                              return (
                                <TableCell key={cell.id}>
                                  <div className="table-actions">
                                    <Button
                                      kind="ghost"
                                      size="sm"
                                      onClick={(event) => {
                                        event.stopPropagation();
                                        handleReorder(item.summaryId, -1);
                                      }}
                                      disabled={item.index === 0 || reorderMutation.isPending}
                                    >
                                      Up
                                    </Button>
                                    <Button
                                      kind="ghost"
                                      size="sm"
                                      onClick={(event) => {
                                        event.stopPropagation();
                                        handleReorder(item.summaryId, 1);
                                      }}
                                      disabled={item.index === rows.length - 1 || reorderMutation.isPending}
                                    >
                                      Down
                                    </Button>
                                    <Button
                                      kind="tertiary"
                                      size="sm"
                                      onClick={(event) => {
                                        event.stopPropagation();
                                        handleMoveItem(item.summaryId);
                                      }}
                                    >
                                      Move
                                    </Button>
                                    <Button
                                      kind="danger--ghost"
                                      size="sm"
                                      onClick={(event) => {
                                        event.stopPropagation();
                                        removeMutation.mutate({
                                          collectionId: selectedCollectionId,
                                          summaryId: item.summaryId,
                                        });
                                      }}
                                      disabled={removeMutation.isPending}
                                    >
                                      Remove
                                    </Button>
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
      </div>

      <Modal
        open={moveSummaryId != null}
        modalHeading="Move item to collection"
        primaryButtonText={moveItemMutation.isPending ? "Moving..." : "Move"}
        secondaryButtonText="Cancel"
        primaryButtonDisabled={!canMoveSubmit}
        onRequestClose={() => {
          if (!moveItemMutation.isPending) {
            setMoveSummaryId(null);
          }
        }}
        onRequestSubmit={() => moveItemMutation.mutate()}
      >
        <div className="digest-form-grid">
          <Select
            id="move-item-target"
            labelText="Target collection"
            value={moveTargetCollectionId}
            onChange={(event) => setMoveTargetCollectionId(event.currentTarget.value)}
            disabled={moveTargetOptions.length === 0}
          >
            {moveTargetOptions.length === 0 ? (
              <SelectItem value="" text="No other collections available" />
            ) : (
              moveTargetOptions.map((collection) => (
                <SelectItem key={collection.id} value={String(collection.id)} text={collection.name} />
              ))
            )}
          </Select>
          <TextInput
            id="move-item-create-target"
            labelText="Or create target collection"
            value={moveNewCollectionName}
            onChange={(event) => setMoveNewCollectionName(event.currentTarget.value)}
            placeholder="Collection name"
          />
        </div>
      </Modal>

      <Modal
        open={deleteModalOpen}
        modalHeading="Delete collection"
        primaryButtonText={deleteMutation.isPending ? "Deleting..." : "Delete"}
        secondaryButtonText="Cancel"
        danger
        onRequestClose={() => {
          if (!deleteMutation.isPending) {
            setDeleteModalOpen(false);
          }
        }}
        onRequestSubmit={() => {
          if (selectedCollectionId) {
            deleteMutation.mutate(selectedCollectionId);
          }
        }}
      >
        <p>
          {selectedCollection
            ? `Delete "${selectedCollection.name}"? This action cannot be undone.`
            : "Delete selected collection?"}
        </p>
      </Modal>
    </section>
  );
}
