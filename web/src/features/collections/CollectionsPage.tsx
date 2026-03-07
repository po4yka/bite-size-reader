import { Fragment, useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Button,
  DataTable,
  InlineLoading,
  InlineNotification,
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
  fetchCollectionItems,
  fetchCollectionTree,
  removeSummaryFromCollection,
} from "../../api/collections";
import type { Collection } from "../../api/types";

function RenderTree({
  collection,
  selectedId,
  onSelect,
}: {
  collection: Collection;
  selectedId: number | null;
  onSelect: (id: number) => void;
}) {
  return (
    <TreeNode
      id={String(collection.id)}
      label={`${collection.name} (${collection.itemCount})`}
      onSelect={() => onSelect(collection.id)}
    >
      {(collection.children ?? []).map((child) => (
        <RenderTree key={child.id} collection={child} selectedId={selectedId} onSelect={onSelect} />
      ))}
    </TreeNode>
  );
}

export default function CollectionsPage() {
  const navigate = useNavigate();
  const params = useParams();
  const queryClient = useQueryClient();
  const [selectedCollectionId, setSelectedCollectionId] = useState<number | null>(null);
  const [newCollectionName, setNewCollectionName] = useState("");

  useEffect(() => {
    const fromRoute = Number(params.id);
    if (Number.isFinite(fromRoute) && fromRoute > 0) {
      setSelectedCollectionId(fromRoute);
    }
  }, [params.id]);

  const treeQuery = useQuery({
    queryKey: ["collections-tree"],
    queryFn: () => fetchCollectionTree(),
  });

  const itemsQuery = useQuery({
    queryKey: ["collection-items", selectedCollectionId],
    queryFn: () => fetchCollectionItems(selectedCollectionId ?? 0),
    enabled: Boolean(selectedCollectionId),
  });

  const createMutation = useMutation({
    mutationFn: (name: string) => createCollection(name),
    onSuccess: (collection) => {
      setNewCollectionName("");
      setSelectedCollectionId(collection.id);
      void queryClient.invalidateQueries({ queryKey: ["collections-tree"] });
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

  const headers = [
    { key: "title", header: "Title" },
    { key: "domain", header: "Domain" },
    { key: "createdAt", header: "Added" },
    { key: "actions", header: "Actions" },
  ];

  const rows = useMemo(() => {
    return (itemsQuery.data ?? []).map((item) => ({
      id: String(item.summaryId),
      title: item.title ?? `Summary #${item.summaryId}`,
      domain: item.domain ?? "",
      createdAt: item.createdAt ? new Date(item.createdAt).toLocaleString() : "",
      actions: item,
    }));
  }, [itemsQuery.data]);

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
          <Button
            kind="secondary"
            onClick={() => createMutation.mutate(newCollectionName.trim())}
            disabled={!newCollectionName.trim() || createMutation.isPending}
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

        <TreeView
          label="Collections"
          hideLabel
          active={selectedCollectionId != null ? String(selectedCollectionId) : undefined}
        >
          {(treeQuery.data ?? []).map((collection) => (
            <Fragment key={collection.id}>
              <RenderTree
                collection={collection}
                selectedId={selectedCollectionId}
                onSelect={(id) => setSelectedCollectionId(id)}
              />
            </Fragment>
          ))}
        </TreeView>
      </div>

      <div className="collections-items">
        <h2>{selectedCollectionId ? `Collection #${selectedCollectionId}` : "Select a collection"}</h2>

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
                                  >
                                    Remove
                                  </Button>
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
    </section>
  );
}
