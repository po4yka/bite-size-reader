import { Fragment, useEffect, useMemo, useState, type KeyboardEvent } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  BracketButton,
  BrutalistCard,
  BrutalistDataTableSkeleton,
  BrutalistModal,
  BrutalistModalBody,
  BrutalistModalFooter,
  BrutalistModalHeader,
  BrutalistTable,
  BrutalistTableContainer,
  MonoInput,
  MonoSelect,
  MonoSelectItem,
  SparkLoading,
  StatusBadge,
  Tag,
  TreeNode,
  TreeView,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "../../design";
import { createCollection, moveCollectionItems } from "../../api/collections";
import type { Collection, CollectionItem } from "../../api/types";
import { queryKeys } from "../../api/queryKeys";
import { QueryErrorNotification } from "../../components/QueryErrorNotification";
import {
  useCollectionTree,
  useCollectionItems,
  useCreateCollection,
  useRenameCollection,
  useDeleteCollection,
  useRemoveFromCollection,
  useReorderCollectionItems,
  useEvaluateSmartCollection,
  useUpdateSmartConditions,
} from "../../hooks/useCollections";
import { useTelegramClosingConfirmation } from "../../hooks/useTelegramClosingConfirmation";
import SmartCollectionEditor, { type SmartCondition } from "./SmartCollectionEditor";

function RenderTree({
  collection,
  onSelect,
}: {
  collection: Collection;
  onSelect: (id: number) => void;
}) {
  const isSmart = collection.collectionType === "smart";
  const label = (
    <span>
      {collection.name} ({collection.itemCount})
      {isSmart && (
        <Tag size="sm" type="blue" style={{ marginLeft: "0.25rem" }}>
          Smart
        </Tag>
      )}
    </span>
  );
  return (
    <TreeNode
      id={String(collection.id)}
      label={label}
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
  const [smartEditorOpen, setSmartEditorOpen] = useState(false);
  const [smartEditMode, setSmartEditMode] = useState(false);

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

  const treeQuery = useCollectionTree();
  const itemsQuery = useCollectionItems(selectedCollectionId);

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

  const createMutation = useCreateCollection();
  const renameMutation = useRenameCollection();
  const deleteMutation = useDeleteCollection();
  const removeMutation = useRemoveFromCollection();
  const reorderMutation = useReorderCollectionItems(selectedCollectionId);
  const evaluateMutation = useEvaluateSmartCollection();
  const updateSmartMutation = useUpdateSmartConditions();

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
      void queryClient.invalidateQueries({ queryKey: queryKeys.collections.all });
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

  const isSmartCollection = selectedCollection?.collectionType === "smart";

  const firstMutationError = [
    createMutation.error,
    renameMutation.error,
    deleteMutation.error,
    removeMutation.error,
    moveItemMutation.error,
    reorderMutation.error,
    evaluateMutation.error,
    updateSmartMutation.error,
  ].find((error): error is Error => error instanceof Error);

  const canCreate = newCollectionName.trim().length > 0;
  const canRename = Boolean(selectedCollectionId) && renameCollectionName.trim().length > 0;

  const canMoveSubmit =
    moveSummaryId != null &&
    (Boolean(moveTargetCollectionId) || moveNewCollectionName.trim().length > 0) &&
    !moveItemMutation.isPending;
  const isDirty =
    newCollectionName.trim().length > 0 ||
    (selectedCollection != null && renameCollectionName.trim() !== selectedCollection.name) ||
    moveSummaryId != null ||
    moveNewCollectionName.trim().length > 0 ||
    createMutation.isPending ||
    renameMutation.isPending ||
    deleteMutation.isPending ||
    moveItemMutation.isPending ||
    removeMutation.isPending ||
    reorderMutation.isPending ||
    evaluateMutation.isPending ||
    updateSmartMutation.isPending;

  useTelegramClosingConfirmation(isDirty);

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

  function handleRowKeyDown(event: KeyboardEvent<HTMLTableRowElement>, summaryId: number): void {
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    navigate(`/library/${summaryId}`);
  }

  return (
    <main
      style={{
        maxWidth: "var(--frost-strip-7)",
        padding: "0 var(--frost-pad-page)",
        display: "flex",
        flexDirection: "column",
        gap: "var(--frost-gap-page)",
      }}
    >
      <div
        className="collections-layout"
        style={{
          display: "grid",
          gridTemplateColumns: "var(--frost-strip-3) 1fr",
          gap: "var(--frost-gap-section)",
          alignItems: "start",
        }}
      >
        {/* Tree panel */}
        <div
          className="collections-tree"
          style={{ display: "flex", flexDirection: "column", gap: "var(--frost-gap-section)" }}
        >
          <h1
            style={{
              fontFamily: "var(--frost-font-mono)",
              fontSize: "var(--frost-type-mono-emph-size)",
              fontWeight: "var(--frost-type-mono-emph-weight)" as React.CSSProperties["fontWeight"],
              letterSpacing: "var(--frost-type-mono-emph-tracking)",
              textTransform: "uppercase",
              color: "var(--frost-ink)",
              margin: 0,
            }}
          >
            Collections
          </h1>

          <div style={{ display: "flex", flexDirection: "column", gap: "var(--frost-gap-row)" }}>
            <MonoInput
              id="new-collection"
              labelText="New collection"
              value={newCollectionName}
              onChange={(event) => setNewCollectionName(event.currentTarget.value)}
            />
            <MonoSelect
              id="new-collection-parent"
              labelText="Create location"
              value={createParentMode}
              onChange={(event) => setCreateParentMode(event.currentTarget.value as "root" | "selected")}
            >
              <MonoSelectItem value="root" text="Top level" />
              <MonoSelectItem
                value="selected"
                text={
                  selectedCollection
                    ? `Inside ${selectedCollection.name}`
                    : "Inside selected collection (pick one first)"
                }
                disabled={!selectedCollection}
              />
            </MonoSelect>
            <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
              <BracketButton
                kind="secondary"
                onClick={() =>
                  createMutation.mutate(
                    {
                      name: newCollectionName.trim(),
                      parentId: createParentMode === "selected" ? selectedCollectionId ?? undefined : undefined,
                    },
                    {
                      onSuccess: (collection) => {
                        setNewCollectionName("");
                        setSelectedCollectionId(collection.id);
                        navigate(`/collections/${collection.id}`);
                      },
                    },
                  )
                }
                disabled={!canCreate || createMutation.isPending}
              >
                Create
              </BracketButton>
              <BracketButton
                kind="tertiary"
                onClick={() => {
                  setSmartEditMode(false);
                  setSmartEditorOpen(true);
                }}
              >
                Create smart collection
              </BracketButton>
            </div>
          </div>

          {treeQuery.isLoading && (
            <SparkLoading description="Loading collections…" status="active" />
          )}
          <QueryErrorNotification error={treeQuery.error} title="Failed to load collections" />

          {firstMutationError && (
            <StatusBadge severity="alarm">
              Collection action failed: {firstMutationError.message}
            </StatusBadge>
          )}

          {selectedCollection && (
            <div style={{ display: "flex", flexDirection: "column", gap: "var(--frost-gap-row)" }}>
              <MonoInput
                id="rename-collection"
                labelText="Rename selected collection"
                value={renameCollectionName}
                onChange={(event) => setRenameCollectionName(event.currentTarget.value)}
              />
              <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
                <BracketButton
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
                </BracketButton>
                <BracketButton
                  kind="danger--ghost"
                  onClick={() => setDeleteModalOpen(true)}
                  disabled={deleteMutation.isPending}
                >
                  Delete
                </BracketButton>
              </div>
            </div>
          )}

          {treeQuery.isSuccess && (treeQuery.data ?? []).length === 0 && (
            <BrutalistCard>
              <div className="page-heading-group">
                <h3
                  style={{
                    fontFamily: "var(--frost-font-mono)",
                    fontSize: "var(--frost-type-mono-emph-size)",
                    fontWeight: "var(--frost-type-mono-emph-weight)" as React.CSSProperties["fontWeight"],
                    textTransform: "uppercase",
                    letterSpacing: "var(--frost-type-mono-emph-tracking)",
                    color: "var(--frost-ink)",
                    margin: "0 0 var(--frost-gap-row) 0",
                  }}
                >
                  No collections yet
                </h3>
                <p
                  style={{
                    fontFamily: "var(--frost-font-mono)",
                    fontSize: "var(--frost-type-mono-body-size)",
                    color: "color-mix(in oklch, var(--frost-ink) 55%, transparent)",
                    margin: 0,
                  }}
                >
                  Collections let you organise your saved articles into named groups. Create your first one above.
                </p>
              </div>
            </BrutalistCard>
          )}

          {(treeQuery.data ?? []).length > 0 && (
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
          )}
        </div>

        {/* Items panel */}
        <div
          className="collections-items"
          style={{ display: "flex", flexDirection: "column", gap: "var(--frost-gap-section)" }}
        >
          <h2
            style={{
              fontFamily: "var(--frost-font-mono)",
              fontSize: "var(--frost-type-mono-emph-size)",
              fontWeight: "var(--frost-type-mono-emph-weight)" as React.CSSProperties["fontWeight"],
              letterSpacing: "var(--frost-type-mono-emph-tracking)",
              textTransform: "uppercase",
              color: "var(--frost-ink)",
              margin: 0,
            }}
          >
            {selectedCollection ? selectedCollection.name : "Select a collection"}
          </h2>

          {selectedCollection && isSmartCollection && (
            <div style={{ display: "flex", flexDirection: "column", gap: "var(--frost-gap-row)" }}>
              <Tag type="blue" size="sm">
                Smart collection
              </Tag>
              {selectedCollection.queryMatchMode && (
                <p
                  style={{
                    fontFamily: "var(--frost-font-mono)",
                    fontSize: "var(--frost-type-mono-body-size)",
                    color: "var(--frost-ink)",
                    margin: 0,
                  }}
                >
                  Match mode:{" "}
                  <strong>
                    {selectedCollection.queryMatchMode === "all" ? "All conditions" : "Any condition"}
                  </strong>
                </p>
              )}
              {selectedCollection.queryConditions && selectedCollection.queryConditions.length > 0 && (
                <ul
                  style={{
                    fontFamily: "var(--frost-font-mono)",
                    fontSize: "var(--frost-type-mono-body-size)",
                    color: "var(--frost-ink)",
                    margin: 0,
                    paddingLeft: "var(--frost-line)",
                  }}
                >
                  {selectedCollection.queryConditions.map((cond, i) => (
                    <li key={i}>
                      {cond.type} {cond.operator} {String(cond.value)}
                    </li>
                  ))}
                </ul>
              )}
              {selectedCollection.lastEvaluatedAt && (
                <p
                  style={{
                    fontFamily: "var(--frost-font-mono)",
                    fontSize: "var(--frost-type-mono-xs-size)",
                    color: "color-mix(in oklch, var(--frost-ink) 55%, transparent)",
                    margin: 0,
                  }}
                >
                  Last evaluated: {new Date(selectedCollection.lastEvaluatedAt).toLocaleString()}
                </p>
              )}
              <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
                <BracketButton
                  kind="tertiary"
                  size="sm"
                  onClick={() => {
                    setSmartEditMode(true);
                    setSmartEditorOpen(true);
                  }}
                >
                  Edit conditions
                </BracketButton>
                <BracketButton
                  kind="secondary"
                  size="sm"
                  onClick={() => selectedCollectionId && evaluateMutation.mutate(selectedCollectionId)}
                  disabled={evaluateMutation.isPending}
                >
                  {evaluateMutation.isPending ? "Evaluating..." : "Re-evaluate"}
                </BracketButton>
              </div>
            </div>
          )}

          {itemsQuery.isLoading && selectedCollectionId && (
            <BrutalistDataTableSkeleton columnCount={headers.length} rowCount={6} showToolbar={false} />
          )}
          <QueryErrorNotification error={itemsQuery.error} title="Failed to load collection items" />

          {selectedCollectionId && !itemsQuery.isLoading && rows.length === 0 && !itemsQuery.error && (
            <BrutalistCard>
              <div className="page-heading-group">
                <h3
                  style={{
                    fontFamily: "var(--frost-font-mono)",
                    fontSize: "var(--frost-type-mono-emph-size)",
                    fontWeight: "var(--frost-type-mono-emph-weight)" as React.CSSProperties["fontWeight"],
                    textTransform: "uppercase",
                    letterSpacing: "var(--frost-type-mono-emph-tracking)",
                    color: "var(--frost-ink)",
                    margin: "0 0 var(--frost-gap-row) 0",
                  }}
                >
                  This collection is empty
                </h3>
                <p
                  style={{
                    fontFamily: "var(--frost-font-mono)",
                    fontSize: "var(--frost-type-mono-body-size)",
                    color: "color-mix(in oklch, var(--frost-ink) 55%, transparent)",
                    margin: 0,
                  }}
                >
                  Add articles to this collection from the Library using the &#34;Add to collection&#34; action.
                </p>
              </div>
            </BrutalistCard>
          )}

          {selectedCollectionId && rows.length > 0 && (
            <BrutalistTable rows={rows} headers={headers}>
              {({ rows, headers, getHeaderProps, getRowProps, getTableProps }) => (
                <BrutalistTableContainer title="Collection items">
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
                        const item = row.cells.find((cell) => cell.info.header === "actions")?.value as {
                          summaryId: number;
                          index: number;
                        };
                        return (
                          <TableRow
                            {...getRowProps({ row })}
                            onClick={() => navigate(`/library/${item.summaryId}`)}
                            onKeyDown={(event) => handleRowKeyDown(event, item.summaryId)}
                            role="link"
                            tabIndex={0}
                            className="clickable-row"
                          >
                            {row.cells.map((cell) => {
                              if (cell.info.header === "actions") {
                                return (
                                  <TableCell key={cell.id}>
                                    {!isSmartCollection && (
                                      <div className="table-actions" style={{ display: "flex", gap: "var(--frost-gap-row)" }}>
                                        <BracketButton
                                          kind="ghost"
                                          size="sm"
                                          onClick={(event) => {
                                            event.stopPropagation();
                                            handleReorder(item.summaryId, -1);
                                          }}
                                          disabled={item.index === 0 || reorderMutation.isPending}
                                        >
                                          Up
                                        </BracketButton>
                                        <BracketButton
                                          kind="ghost"
                                          size="sm"
                                          onClick={(event) => {
                                            event.stopPropagation();
                                            handleReorder(item.summaryId, 1);
                                          }}
                                          disabled={item.index === rows.length - 1 || reorderMutation.isPending}
                                        >
                                          Down
                                        </BracketButton>
                                        <BracketButton
                                          kind="tertiary"
                                          size="sm"
                                          onClick={(event) => {
                                            event.stopPropagation();
                                            handleMoveItem(item.summaryId);
                                          }}
                                        >
                                          Move
                                        </BracketButton>
                                        <BracketButton
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
                                        </BracketButton>
                                      </div>
                                    )}
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
                </BrutalistTableContainer>
              )}
            </BrutalistTable>
          )}
        </div>
      </div>

      <BrutalistModal
        open={moveSummaryId != null}
        onRequestClose={() => {
          if (!moveItemMutation.isPending) {
            setMoveSummaryId(null);
          }
        }}
        onRequestSubmit={() => moveItemMutation.mutate()}
      >
        <BrutalistModalHeader title="Move item to collection" />
        <BrutalistModalBody>
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--frost-gap-row)" }}>
            <MonoSelect
              id="move-item-target"
              labelText="Target collection"
              value={moveTargetCollectionId}
              onChange={(event) => setMoveTargetCollectionId(event.currentTarget.value)}
              disabled={moveTargetOptions.length === 0}
            >
              {moveTargetOptions.length === 0 ? (
                <MonoSelectItem value="" text="No other collections available" />
              ) : (
                moveTargetOptions.map((collection) => (
                  <MonoSelectItem key={collection.id} value={String(collection.id)} text={collection.name} />
                ))
              )}
            </MonoSelect>
            <MonoInput
              id="move-item-create-target"
              labelText="Or create target collection"
              value={moveNewCollectionName}
              onChange={(event) => setMoveNewCollectionName(event.currentTarget.value)}
              placeholder="Collection name…"
            />
          </div>
        </BrutalistModalBody>
        <BrutalistModalFooter
          primaryButtonText={moveItemMutation.isPending ? "Moving…" : "Move"}
          primaryButtonDisabled={!canMoveSubmit}
          secondaryButtonText="Cancel"
          onRequestClose={() => {
            if (!moveItemMutation.isPending) {
              setMoveSummaryId(null);
            }
          }}
          onRequestSubmit={() => moveItemMutation.mutate()}
        />
      </BrutalistModal>

      <SmartCollectionEditor
        key={smartEditMode ? `edit-${selectedCollectionId}` : "create"}
        open={smartEditorOpen}
        onClose={() => setSmartEditorOpen(false)}
        onSave={(data) => {
          if (smartEditMode && selectedCollectionId) {
            updateSmartMutation.mutate(
              {
                collectionId: selectedCollectionId,
                name: data.name,
                queryConditions: data.conditions,
                queryMatchMode: data.matchMode,
              },
              { onSuccess: () => setSmartEditorOpen(false) },
            );
          } else {
            createMutation.mutate(
              {
                name: data.name,
                parentId: createParentMode === "selected" ? selectedCollectionId ?? undefined : undefined,
                smartFields: {
                  collection_type: "smart",
                  query_conditions: data.conditions,
                  query_match_mode: data.matchMode,
                },
              },
              {
                onSuccess: (collection) => {
                  setSmartEditorOpen(false);
                  setSelectedCollectionId(collection.id);
                  navigate(`/collections/${collection.id}`);
                },
              },
            );
          }
        }}
        initialData={
          smartEditMode && selectedCollection?.collectionType === "smart"
            ? {
                name: selectedCollection.name,
                conditions: (selectedCollection.queryConditions ?? []) as SmartCondition[],
                matchMode: selectedCollection.queryMatchMode ?? "all",
              }
            : undefined
        }
        isSaving={createMutation.isPending || updateSmartMutation.isPending}
      />

      <BrutalistModal
        open={deleteModalOpen}
        danger
        onRequestClose={() => {
          if (!deleteMutation.isPending) {
            setDeleteModalOpen(false);
          }
        }}
        onRequestSubmit={() => {
          if (selectedCollectionId) {
            deleteMutation.mutate(selectedCollectionId, {
              onSuccess: (_, collectionId) => {
                if (selectedCollectionId === collectionId) {
                  setSelectedCollectionId(null);
                  navigate("/collections");
                }
                setDeleteModalOpen(false);
              },
            });
          }
        }}
      >
        <BrutalistModalHeader title="Delete collection" />
        <BrutalistModalBody>
          <p
            style={{
              fontFamily: "var(--frost-font-mono)",
              fontSize: "var(--frost-type-mono-body-size)",
              color: "var(--frost-ink)",
              margin: 0,
            }}
          >
            {selectedCollection
              ? `Delete "${selectedCollection.name}"? This action cannot be undone.`
              : "Delete selected collection?"}
          </p>
        </BrutalistModalBody>
        <BrutalistModalFooter
          primaryButtonText={deleteMutation.isPending ? "Deleting…" : "Delete"}
          secondaryButtonText="Cancel"
          onRequestClose={() => {
            if (!deleteMutation.isPending) {
              setDeleteModalOpen(false);
            }
          }}
          onRequestSubmit={() => {
            if (selectedCollectionId) {
              deleteMutation.mutate(selectedCollectionId, {
                onSuccess: (_, collectionId) => {
                  if (selectedCollectionId === collectionId) {
                    setSelectedCollectionId(null);
                    navigate("/collections");
                  }
                  setDeleteModalOpen(false);
                },
              });
            }
          }}
        />
      </BrutalistModal>
    </main>
  );
}
