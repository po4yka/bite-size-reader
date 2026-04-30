import React, { useCallback, useMemo, useState } from "react";
import {
  Button,
  DataTableSkeleton,
  Dropdown,
  InlineNotification,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableHeader,
  TableRow,
  TextInput,
  Tile,
} from "../../design";
import {
  DataTable as BrutalistTable,
  TableExpandCell,
  TableExpandHeaderCell,
  TableSelectCell,
  TableSelectHeaderCell,
} from "../../design/table/BrutalistTable";
import type { DigestCategory } from "../../api/digest";
import {
  useAssignCategory,
  useBulkAssignCategory,
  useBulkUnsubscribe,
  useDigestCategories,
  useDigestChannels,
  useSubscribeChannel,
  useTriggerDigest,
  useTriggerSingleChannelDigest,
  useUnsubscribeChannel,
} from "../../hooks/useDigest";
import { useTelegramMainButton } from "../../hooks/useTelegramMainButton";
import { BatchCategoryModal } from "./BatchCategoryModal";
import { CategoryManagementModal } from "./CategoryManagementModal";
import { ChannelPostsPreview } from "./ChannelPostsPreview";
import { ChannelResolvePreview } from "./ChannelResolvePreview";

export function ChannelsTab({ isOwner, isActive }: { isOwner: boolean; isActive: boolean }) {
  const [ownerChannel, setOwnerChannel] = useState("");
  const [categoryFilter, setCategoryFilter] = useState<number | null | "all">("all");
  const [categoryModalOpen, setCategoryModalOpen] = useState(false);
  const [batchCategoryModalOpen, setBatchCategoryModalOpen] = useState(false);
  const [batchSelectedIds, setBatchSelectedIds] = useState<string[]>([]);

  const channelsQuery = useDigestChannels();
  const categoriesQuery = useDigestCategories();

  const categories: DigestCategory[] = useMemo(
    () => (Array.isArray(categoriesQuery.data) ? categoriesQuery.data : []),
    [categoriesQuery.data],
  );

  const subscribeMutation = useSubscribeChannel();
  const unsubscribeMutation = useUnsubscribeChannel();
  const bulkUnsubscribeMutation = useBulkUnsubscribe();
  const assignCategoryMutation = useAssignCategory();
  const bulkAssignMutation = useBulkAssignCategory();
  const triggerMutation = useTriggerDigest();
  const ownerTriggerMutation = useTriggerSingleChannelDigest();

  const canTriggerDigestNow = (channelsQuery.data?.activeCount ?? 0) > 0;
  const isChannelsInitialLoading = channelsQuery.isLoading && !channelsQuery.data;

  const handleTriggerDigestNow = useCallback(() => {
    if (!canTriggerDigestNow || triggerMutation.isPending) return;
    triggerMutation.mutate();
  }, [canTriggerDigestNow, triggerMutation]);

  useTelegramMainButton({
    visible: isActive,
    text: "Generate Digest Now",
    disabled: !canTriggerDigestNow || triggerMutation.isPending,
    loading: triggerMutation.isPending,
    onClick: handleTriggerDigestNow,
  });

  const categoryLookup = useMemo(() => {
    const map = new Map<number, string>();
    for (const c of categories) {
      map.set(c.id, c.name);
    }
    return map;
  }, [categories]);

  const filteredChannels = useMemo(() => {
    const channels = channelsQuery.data?.channels ?? [];
    if (categoryFilter === "all") return channels;
    return channels.filter((ch) => ch.categoryId === categoryFilter);
  }, [channelsQuery.data?.channels, categoryFilter]);

  const headers = [
    { key: "username", header: "Channel" },
    { key: "title", header: "Title" },
    { key: "category", header: "Category" },
    { key: "fetchErrorCount", header: "Errors" },
    { key: "createdAt", header: "Subscribed" },
    { key: "actions", header: "Actions" },
  ];

  const rows = useMemo(
    () =>
      filteredChannels.map((channel) => ({
        id: String(channel.id),
        username: `@${channel.username}`,
        title: channel.title ?? "-",
        category: channel.categoryId != null ? (categoryLookup.get(channel.categoryId) ?? "-") : "-",
        fetchErrorCount: channel.fetchErrorCount,
        createdAt: new Date(channel.createdAt).toLocaleString(),
        actions: channel.username,
      })),
    [filteredChannels, categoryLookup],
  );

  // Build username lookup from channel id (string) -> username
  const idToUsername = useMemo(() => {
    const map = new Map<string, string>();
    for (const ch of channelsQuery.data?.channels ?? []) {
      map.set(String(ch.id), ch.username);
    }
    return map;
  }, [channelsQuery.data?.channels]);

  const categoryFilterItems = useMemo(
    () => [
      { id: "all" as const, label: "All categories" },
      { id: "none" as const, label: "No category" },
      ...categories.map((c) => ({ id: String(c.id), label: c.name })),
    ],
    [categories],
  );

  const handleBulkUnsubscribe = (selectedRowIds: readonly { id: string }[]) => {
    const usernames = selectedRowIds
      .map((r) => idToUsername.get(r.id))
      .filter((u): u is string => u != null);
    if (usernames.length > 0) {
      bulkUnsubscribeMutation.mutate(usernames);
    }
  };

  const handleBulkCategory = (categoryId: number | null) => {
    const ids = batchSelectedIds.map(Number).filter((n) => !Number.isNaN(n));
    if (ids.length > 0) {
      bulkAssignMutation.mutate({ ids, categoryId }, { onSuccess: () => setBatchCategoryModalOpen(false) });
    }
  };

  return (
    <div className="page-section">
      <Tile>
        <h3>Subscriptions</h3>

        <ChannelResolvePreview
          onConfirmSubscribe={(username) => subscribeMutation.mutate(username)}
          isSubscribing={subscribeMutation.isPending}
        />

        {(channelsQuery.error || subscribeMutation.error || unsubscribeMutation.error || bulkUnsubscribeMutation.error) && (
          <InlineNotification
            kind="error"
            title="Digest channel operation failed"
            subtitle={
              (
                (channelsQuery.error ||
                  subscribeMutation.error ||
                  unsubscribeMutation.error ||
                  bulkUnsubscribeMutation.error) as Error | null
              )?.message ?? "Unknown error"
            }
            hideCloseButton
          />
        )}

        {channelsQuery.data && (
          <p className="muted">
            {channelsQuery.data.unlimitedChannels || channelsQuery.data.maxChannels == null
              ? `${channelsQuery.data.activeCount} channels subscribed`
              : `${channelsQuery.data.activeCount}/${channelsQuery.data.maxChannels} slots used`}
          </p>
        )}

        {isChannelsInitialLoading && <DataTableSkeleton columnCount={headers.length} rowCount={6} showToolbar={false} />}

        {!isChannelsInitialLoading && (
          <BrutalistTable rows={rows} headers={headers} radio={false} isSortable={false}>
            {({
              rows,
              headers,
              getHeaderProps,
              getRowProps,
              getTableProps,
              getSelectionProps,
              getTableContainerProps,
              getBatchActionProps,
              getExpandedRowProps,
              selectedRows,
            }) => {
              const batchActionProps = getBatchActionProps();
              const allSelProps = getSelectionProps();
              return (
                <TableContainer title="Digest channels" {...getTableContainerProps()}>
                  {/* Frost-styled toolbar */}
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      padding: "8px 16px",
                      borderBottom: "1px solid color-mix(in oklch, var(--frost-ink) 50%, transparent)",
                      backgroundColor: "var(--frost-page)",
                      gap: "8px",
                      flexWrap: "wrap",
                    }}
                  >
                    {/* Batch action bar — shown when rows are selected */}
                    {batchActionProps.shouldShowBatchActions && (
                      <div
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: "8px",
                          fontFamily: "var(--frost-font-mono)",
                          fontSize: "var(--frost-type-mono-xs-size)",
                        }}
                      >
                        <span style={{ color: "var(--frost-ink)", opacity: 0.7 }}>
                          {batchActionProps.totalSelected} selected
                        </span>
                        <Button
                          kind="danger--ghost"
                          size="sm"
                          onClick={() => handleBulkUnsubscribe(selectedRows)}
                        >
                          Unsubscribe Selected
                        </Button>
                        <Button
                          kind="ghost"
                          size="sm"
                          onClick={() => {
                            setBatchSelectedIds(selectedRows.map((r) => r.id));
                            setBatchCategoryModalOpen(true);
                          }}
                        >
                          Set Category
                        </Button>
                        <Button
                          kind="ghost"
                          size="sm"
                          onClick={batchActionProps.onCancel}
                        >
                          Cancel
                        </Button>
                      </div>
                    )}
                    {/* Normal toolbar content */}
                    {!batchActionProps.shouldShowBatchActions && (
                      <div style={{ display: "flex", alignItems: "center", gap: "8px", marginLeft: "auto" }}>
                        <Dropdown
                          id="category-filter"
                          titleText=""
                          label="Filter by category"
                          size="sm"
                          items={categoryFilterItems}
                          itemToString={(item) => item?.label ?? ""}
                          onChange={({ selectedItem }) => {
                            if (!selectedItem || selectedItem.id === "all") {
                              setCategoryFilter("all");
                            } else if (selectedItem.id === "none") {
                              setCategoryFilter(null);
                            } else {
                              setCategoryFilter(Number(selectedItem.id));
                            }
                          }}
                        />
                        <Button kind="ghost" size="sm" onClick={() => setCategoryModalOpen(true)}>
                          Manage Categories
                        </Button>
                      </div>
                    )}
                  </div>
                  <Table {...getTableProps()}>
                    <TableHead>
                      <TableRow>
                        <TableSelectHeaderCell
                          checked={allSelProps.checked as boolean}
                          onSelect={allSelProps.onSelect as () => void}
                          id={allSelProps.id as string}
                        />
                        <TableExpandHeaderCell />
                        {headers.map((header) => (
                          <TableHeader key={header.key} {...getHeaderProps({ header })}>{header.header}</TableHeader>
                        ))}
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {rows.map((row) => {
                        const username = row.cells.find((cell) => cell.info.header === "actions")?.value as string;
                        const subscriptionId = Number(row.id);
                        const rowSelProps = getSelectionProps({ row });
                        const expandedProps = getExpandedRowProps({ row });
                        const rowProps = getRowProps({ row });
                        return (
                          <React.Fragment key={row.id}>
                            <TableRow {...rowProps}>
                              <TableSelectCell
                                id={rowSelProps.id as string}
                                name={rowSelProps.name as string}
                                checked={rowSelProps.checked as boolean}
                                onSelect={rowSelProps.onSelect as () => void}
                              />
                              <TableExpandCell
                                isExpanded={row.isExpanded ?? false}
                                onToggle={expandedProps.onToggle as () => void}
                              />
                              {row.cells.map((cell) => {
                                if (cell.info.header === "actions") {
                                  return (
                                    <TableCell key={cell.id}>
                                      <Button
                                        kind="danger--ghost"
                                        size="sm"
                                        disabled={unsubscribeMutation.isPending}
                                        onClick={() => unsubscribeMutation.mutate(username)}
                                      >
                                        Remove
                                      </Button>
                                    </TableCell>
                                  );
                                }
                                if (cell.info.header === "category") {
                                  return (
                                    <TableCell key={cell.id}>
                                      <Dropdown
                                        id={`cat-${row.id}`}
                                        titleText=""
                                        label="-"
                                        size="sm"
                                        items={[
                                          { id: null as number | null, label: "No category" },
                                          ...categories.map((c) => ({ id: c.id as number | null, label: c.name })),
                                        ]}
                                        itemToString={(item) => item?.label ?? ""}
                                        selectedItem={
                                          (() => {
                                            const ch = (channelsQuery.data?.channels ?? []).find(
                                              (c) => String(c.id) === row.id,
                                            );
                                            if (!ch || ch.categoryId == null) return { id: null, label: "No category" };
                                            const cat = categories.find((c) => c.id === ch.categoryId);
                                            return cat ? { id: cat.id, label: cat.name } : { id: null, label: "No category" };
                                          })()
                                        }
                                        onChange={({ selectedItem }) => {
                                          if (selectedItem !== undefined) {
                                            assignCategoryMutation.mutate({
                                              subscriptionId,
                                              categoryId: selectedItem?.id ?? null,
                                            });
                                          }
                                        }}
                                      />
                                    </TableCell>
                                  );
                                }
                                return <TableCell key={cell.id}>{String(cell.value)}</TableCell>;
                              })}
                            </TableRow>
                            {row.isExpanded && (
                              <TableRow>
                                <TableCell
                                  colSpan={headers.length + 2}
                                  style={{ padding: "16px" }}
                                >
                                  <ChannelPostsPreview username={username} />
                                </TableCell>
                              </TableRow>
                            )}
                          </React.Fragment>
                        );
                      })}
                    </TableBody>
                  </Table>
                </TableContainer>
              );
            }}
          </BrutalistTable>
        )}

        <div className="form-actions">
          <Button
            disabled={!canTriggerDigestNow || triggerMutation.isPending}
            onClick={handleTriggerDigestNow}
          >
            Generate Digest Now
          </Button>
          {triggerMutation.isSuccess && (
            <InlineNotification
              kind="success"
              title="Digest queued"
              subtitle={`Correlation ID: ${triggerMutation.data.correlationId}`}
              hideCloseButton
            />
          )}
        </div>

        {isOwner && (
          <>
            <h4>Owner: Trigger single-channel digest</h4>
            <div className="form-actions">
              <TextInput
                id="owner-channel-input"
                labelText="Channel"
                placeholder="@channel_name..."
                value={ownerChannel}
                onChange={(event) => setOwnerChannel(event.currentTarget.value)}
              />
              <Button
                kind="tertiary"
                disabled={!ownerChannel.trim() || ownerTriggerMutation.isPending}
                onClick={() => ownerTriggerMutation.mutate(ownerChannel.trim(), { onSuccess: () => setOwnerChannel("") })}
              >
                Trigger Channel Digest
              </Button>
            </div>

            {ownerTriggerMutation.error && (
              <InlineNotification
                kind="error"
                title="Single-channel trigger failed"
                subtitle={
                  ownerTriggerMutation.error instanceof Error
                    ? ownerTriggerMutation.error.message
                    : "Unknown error"
                }
                hideCloseButton
              />
            )}

            {ownerTriggerMutation.isSuccess && (
              <InlineNotification
                kind="success"
                title="Single-channel digest queued"
                subtitle={`Channel: @${ownerTriggerMutation.data.channel}`}
                hideCloseButton
              />
            )}
          </>
        )}
      </Tile>

      <CategoryManagementModal
        open={categoryModalOpen}
        onClose={() => setCategoryModalOpen(false)}
        categories={categories}
      />

      <BatchCategoryModal
        open={batchCategoryModalOpen}
        onClose={() => setBatchCategoryModalOpen(false)}
        categories={categories}
        onAssign={handleBulkCategory}
        isPending={bulkAssignMutation.isPending}
      />
    </div>
  );
}
