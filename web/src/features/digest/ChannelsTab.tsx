import React, { useCallback, useMemo, useState } from "react";
import {
  Button,
  DataTable,
  DataTableSkeleton,
  Dropdown,
  InlineNotification,
  Table,
  TableBatchAction,
  TableBatchActions,
  TableBody,
  TableCell,
  TableContainer,
  TableExpandHeader,
  TableExpandRow,
  TableExpandedRow,
  TableHead,
  TableHeader,
  TableRow,
  TableSelectAll,
  TableSelectRow,
  TableToolbar,
  TableToolbarContent,
  TextInput,
  Tile,
} from "@carbon/react";
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
          <DataTable rows={rows} headers={headers} radio={false} isSortable={false}>
            {({
              rows,
              headers,
              getHeaderProps,
              getRowProps,
              getTableProps,
              getSelectionProps,
              getTableContainerProps,
              getBatchActionProps,
              selectedRows,
            }) => {
              const batchActionProps = getBatchActionProps();
              return (
                <TableContainer title="Digest channels" {...getTableContainerProps()}>
                  <TableToolbar>
                    <TableBatchActions {...batchActionProps}>
                      <TableBatchAction
                        tabIndex={batchActionProps.shouldShowBatchActions ? 0 : -1}
                        onClick={() => handleBulkUnsubscribe(selectedRows)}
                      >
                        Unsubscribe Selected
                      </TableBatchAction>
                      <TableBatchAction
                        tabIndex={batchActionProps.shouldShowBatchActions ? 0 : -1}
                        onClick={() => {
                          setBatchSelectedIds(selectedRows.map((r) => r.id));
                          setBatchCategoryModalOpen(true);
                        }}
                      >
                        Set Category
                      </TableBatchAction>
                    </TableBatchActions>
                    <TableToolbarContent>
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
                    </TableToolbarContent>
                  </TableToolbar>
                  <Table {...getTableProps()}>
                    <TableHead>
                      <TableRow>
                        <TableSelectAll {...getSelectionProps()} />
                        <TableExpandHeader />
                        {headers.map((header) => (
                          <TableHeader {...getHeaderProps({ header })}>{header.header}</TableHeader>
                        ))}
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {rows.map((row) => {
                        const username = row.cells.find((cell) => cell.info.header === "actions")?.value as string;
                        const subscriptionId = Number(row.id);
                        return (
                          <React.Fragment key={row.id}>
                            <TableExpandRow {...getRowProps({ row })}>
                              <TableSelectRow {...getSelectionProps({ row })} />
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
                            </TableExpandRow>
                            <TableExpandedRow colSpan={headers.length + 2}>
                              <ChannelPostsPreview username={username} />
                            </TableExpandedRow>
                          </React.Fragment>
                        );
                      })}
                    </TableBody>
                  </Table>
                </TableContainer>
              );
            }}
          </DataTable>
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
