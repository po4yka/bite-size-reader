import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Button,
  ComposedModal,
  DataTable,
  DataTableSkeleton,
  Dropdown,
  InlineLoading,
  InlineNotification,
  ModalBody,
  ModalFooter,
  ModalHeader,
  NumberInput,
  Pagination,
  Select,
  SelectItem,
  Tab,
  TabList,
  TabPanel,
  TabPanels,
  Tabs,
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
  Tag,
  TextInput,
  Tile,
  TimePicker,
} from "@carbon/react";
import { useAuth } from "../../auth/AuthProvider";
import {
  assignDigestCategory,
  bulkAssignDigestCategory,
  bulkUnsubscribeDigest,
  createDigestCategory,
  deleteDigestCategory,
  fetchDigestChannelPosts,
  fetchDigestChannels,
  fetchDigestHistory,
  fetchDigestPreferences,
  listDigestCategories,
  resolveDigestChannel,
  subscribeDigestChannel,
  triggerDigestNow,
  triggerSingleChannelDigest,
  unsubscribeDigestChannel,
  updateDigestCategory,
  updateDigestPreferences,
} from "../../api/digest";
import type { DigestCategory, DigestChannelPost, ResolvedChannel } from "../../api/digest";
import { useTelegramMainButton } from "../../hooks/useTelegramMainButton";

const HISTORY_PAGE_SIZE = 20;

function DigestUnavailableNotice() {
  return (
    <InlineNotification
      kind="warning"
      title="Digest requires Telegram WebApp context"
      subtitle="Digest endpoints require Telegram initData, so this section is available when opened from Telegram Mini App context."
      hideCloseButton
    />
  );
}

/* ---------- Channel post preview (expandable row content) ---------- */

function ChannelPostsPreview({ username }: { username: string }) {
  const postsQuery = useQuery({
    queryKey: ["channel-posts", username],
    queryFn: () => fetchDigestChannelPosts(username),
  });

  if (postsQuery.isLoading) {
    return <InlineLoading description="Loading posts..." />;
  }

  if (postsQuery.error) {
    return (
      <InlineNotification
        kind="error"
        title="Failed to load posts"
        subtitle={postsQuery.error instanceof Error ? postsQuery.error.message : "Unknown error"}
        hideCloseButton
      />
    );
  }

  const posts: DigestChannelPost[] = postsQuery.data?.posts ?? [];

  if (posts.length === 0) {
    return <p className="muted">No recent posts found.</p>;
  }

  return (
    <ul className="digest-list">
      {posts.map((post) => (
        <li
          key={post.id}
          style={{
            padding: "0.5rem 0",
            borderBottom: "1px solid var(--cds-border-subtle)",
          }}
        >
          <div className="digest-list-item-row">
            <span className="muted digest-text-xs">
              {new Date(post.date).toLocaleString()}
            </span>
            <Tag type="blue" size="sm">
              {post.contentType}
            </Tag>
            {post.views != null && (
              <span className="muted digest-text-xs">
                {post.views} views
              </span>
            )}
          </div>
          <p style={{ margin: 0, fontSize: "0.875rem" }}>
            {post.text ? (post.text.length > 200 ? `${post.text.slice(0, 200)}...` : post.text) : "(no text)"}
          </p>
        </li>
      ))}
    </ul>
  );
}

/* ---------- Category management modal ---------- */

function CategoryManagementModal({
  open,
  onClose,
  categories,
}: {
  open: boolean;
  onClose: () => void;
  categories: DigestCategory[];
}) {
  const queryClient = useQueryClient();
  const [newCategoryName, setNewCategoryName] = useState("");
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editingName, setEditingName] = useState("");

  const createMutation = useMutation({
    mutationFn: (name: string) => createDigestCategory(name),
    onSuccess: () => {
      setNewCategoryName("");
      void queryClient.invalidateQueries({ queryKey: ["digest-categories"] });
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, name }: { id: number; name: string }) => updateDigestCategory(id, name),
    onSuccess: () => {
      setEditingId(null);
      setEditingName("");
      void queryClient.invalidateQueries({ queryKey: ["digest-categories"] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => deleteDigestCategory(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["digest-categories"] });
      void queryClient.invalidateQueries({ queryKey: ["digest-channels"] });
    },
  });

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
            onClick={() => createMutation.mutate(newCategoryName.trim())}
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
                    onClick={() => updateMutation.mutate({ id: cat.id, name: editingName.trim() })}
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

/* ---------- Resolve / preview step ---------- */

function ChannelResolvePreview({
  onConfirmSubscribe,
  isSubscribing,
}: {
  onConfirmSubscribe: (username: string) => void;
  isSubscribing: boolean;
}) {
  const [input, setInput] = useState("");
  const [resolvedData, setResolvedData] = useState<ResolvedChannel | null>(null);

  const resolveMutation = useMutation({
    mutationFn: (username: string) => resolveDigestChannel(username),
    onSuccess: (data) => setResolvedData(data),
  });

  const handleResolve = () => {
    const trimmed = input.trim();
    if (!trimmed) return;
    setResolvedData(null);
    resolveMutation.mutate(trimmed);
  };

  const handleConfirm = () => {
    if (!resolvedData) return;
    onConfirmSubscribe(resolvedData.username);
    setInput("");
    setResolvedData(null);
  };

  return (
    <>
      <div className="form-actions">
        <TextInput
          id="digest-subscribe-input"
          labelText="Channel username"
          placeholder="@channel_name or t.me/channel..."
          value={input}
          onChange={(event) => {
            setInput(event.currentTarget.value);
            setResolvedData(null);
          }}
        />
        <Button
          kind="secondary"
          disabled={!input.trim() || resolveMutation.isPending}
          onClick={handleResolve}
        >
          Preview
        </Button>
      </div>

      {resolveMutation.isPending && <InlineLoading description="Resolving channel..." />}

      {resolveMutation.error && (
        <InlineNotification
          kind="error"
          title="Channel resolve failed"
          subtitle={resolveMutation.error instanceof Error ? resolveMutation.error.message : "Unknown error"}
          hideCloseButton
        />
      )}

      {resolvedData && (
        <Tile style={{ marginTop: "0.5rem" }}>
          <h4>@{resolvedData.username}</h4>
          {resolvedData.title && <p><strong>{resolvedData.title}</strong></p>}
          {resolvedData.description && (
            <p className="muted digest-text-sm">
              {resolvedData.description.length > 300
                ? `${resolvedData.description.slice(0, 300)}...`
                : resolvedData.description}
            </p>
          )}
          {resolvedData.memberCount != null && (
            <p className="muted digest-text-xs">
              {resolvedData.memberCount.toLocaleString()} members
            </p>
          )}
          <Button
            kind="primary"
            size="sm"
            disabled={isSubscribing}
            onClick={handleConfirm}
            style={{ marginTop: "0.5rem" }}
          >
            Confirm Subscribe
          </Button>
        </Tile>
      )}
    </>
  );
}

/* ---------- Batch category picker modal ---------- */

function BatchCategoryModal({
  open,
  onClose,
  categories,
  onAssign,
  isPending,
}: {
  open: boolean;
  onClose: () => void;
  categories: DigestCategory[];
  onAssign: (categoryId: number | null) => void;
  isPending: boolean;
}) {
  const [selected, setSelected] = useState<{ id: number | null; label: string } | null>(null);

  const items = [
    { id: null as number | null, label: "No category" },
    ...categories.map((c) => ({ id: c.id as number | null, label: c.name })),
  ];

  return (
    <ComposedModal open={open} onClose={onClose}>
      <ModalHeader title="Set Category" />
      <ModalBody>
        <Dropdown
          id="batch-category-dropdown"
          titleText="Category"
          label="Select a category"
          items={items}
          itemToString={(item) => item?.label ?? ""}
          onChange={({ selectedItem }) => setSelected(selectedItem ?? null)}
        />
      </ModalBody>
      <ModalFooter>
        <Button kind="secondary" onClick={onClose}>
          Cancel
        </Button>
        <Button
          kind="primary"
          disabled={selected === null || isPending}
          onClick={() => {
            if (selected !== null) {
              onAssign(selected.id);
            }
          }}
        >
          Apply
        </Button>
      </ModalFooter>
    </ComposedModal>
  );
}

/* ---------- Channels tab ---------- */

function ChannelsTab({ isOwner, isActive }: { isOwner: boolean; isActive: boolean }) {
  const queryClient = useQueryClient();
  const [ownerChannel, setOwnerChannel] = useState("");
  const [categoryFilter, setCategoryFilter] = useState<number | null | "all">("all");
  const [categoryModalOpen, setCategoryModalOpen] = useState(false);
  const [batchCategoryModalOpen, setBatchCategoryModalOpen] = useState(false);
  const [batchSelectedIds, setBatchSelectedIds] = useState<string[]>([]);

  const channelsQuery = useQuery({
    queryKey: ["digest-channels"],
    queryFn: fetchDigestChannels,
  });

  const categoriesQuery = useQuery({
    queryKey: ["digest-categories"],
    queryFn: listDigestCategories,
  });

  const categories: DigestCategory[] = useMemo(
    () => (Array.isArray(categoriesQuery.data) ? categoriesQuery.data : []),
    [categoriesQuery.data],
  );

  const subscribeMutation = useMutation({
    mutationFn: (username: string) => subscribeDigestChannel(username),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["digest-channels"] });
    },
  });

  const unsubscribeMutation = useMutation({
    mutationFn: (username: string) => unsubscribeDigestChannel(username),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["digest-channels"] });
    },
  });

  const bulkUnsubscribeMutation = useMutation({
    mutationFn: (usernames: string[]) => bulkUnsubscribeDigest(usernames),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["digest-channels"] });
    },
  });

  const assignCategoryMutation = useMutation({
    mutationFn: ({ subscriptionId, categoryId }: { subscriptionId: number; categoryId: number | null }) =>
      assignDigestCategory(subscriptionId, categoryId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["digest-channels"] });
    },
  });

  const bulkAssignMutation = useMutation({
    mutationFn: ({ ids, categoryId }: { ids: number[]; categoryId: number | null }) =>
      bulkAssignDigestCategory(ids, categoryId),
    onSuccess: () => {
      setBatchCategoryModalOpen(false);
      void queryClient.invalidateQueries({ queryKey: ["digest-channels"] });
    },
  });

  const triggerMutation = useMutation({
    mutationFn: triggerDigestNow,
  });

  const ownerTriggerMutation = useMutation({
    mutationFn: (username: string) => triggerSingleChannelDigest(username),
    onSuccess: () => setOwnerChannel(""),
  });

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
      bulkAssignMutation.mutate({ ids, categoryId });
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
                onClick={() => ownerTriggerMutation.mutate(ownerChannel.trim())}
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

function PreferencesTab() {
  const queryClient = useQueryClient();

  const preferencesQuery = useQuery({
    queryKey: ["digest-preferences"],
    queryFn: fetchDigestPreferences,
  });

  const [deliveryTime, setDeliveryTime] = useState("09:00");
  const [timezone, setTimezone] = useState("UTC");
  const [hoursLookback, setHoursLookback] = useState(24);
  const [maxPostsPerDigest, setMaxPostsPerDigest] = useState(20);
  const [minRelevanceScore, setMinRelevanceScore] = useState(0.3);

  useEffect(() => {
    if (!preferencesQuery.data) return;
    setDeliveryTime(preferencesQuery.data.deliveryTime);
    setTimezone(preferencesQuery.data.timezone);
    setHoursLookback(preferencesQuery.data.hoursLookback);
    setMaxPostsPerDigest(preferencesQuery.data.maxPostsPerDigest);
    setMinRelevanceScore(preferencesQuery.data.minRelevanceScore);
  }, [preferencesQuery.data]);

  const saveMutation = useMutation({
    mutationFn: () =>
      updateDigestPreferences({
        delivery_time: deliveryTime,
        timezone,
        hours_lookback: hoursLookback,
        max_posts_per_digest: maxPostsPerDigest,
        min_relevance_score: minRelevanceScore,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["digest-preferences"] });
    },
  });

  const data = preferencesQuery.data;

  return (
    <div className="page-section">
      <Tile>
        <h3>Digest preferences</h3>

        {preferencesQuery.isLoading && <InlineLoading description="Loading preferences..." />}

        {(preferencesQuery.error || saveMutation.error) && (
          <InlineNotification
            kind="error"
            title="Digest preference operation failed"
            subtitle={
              (preferencesQuery.error || saveMutation.error) instanceof Error
                ? ((preferencesQuery.error || saveMutation.error) as Error).message
                : "Unknown error"
            }
            hideCloseButton
          />
        )}

        {data && (
          <div className="digest-form-grid">
            <TimePicker
              id="digest-delivery-time"
              labelText={`Delivery time (${data.deliveryTimeSource})`}
              value={deliveryTime}
              onChange={(event) => setDeliveryTime(event.currentTarget.value)}
            />

            <Select
              id="digest-timezone"
              labelText={`Timezone (${data.timezoneSource})`}
              value={timezone}
              onChange={(event) => setTimezone(event.currentTarget.value)}
            >
              <SelectItem text="UTC" value="UTC" />
              <SelectItem text="Europe/London" value="Europe/London" />
              <SelectItem text="Europe/Moscow" value="Europe/Moscow" />
              <SelectItem text="US/Eastern" value="US/Eastern" />
              <SelectItem text="US/Pacific" value="US/Pacific" />
              <SelectItem text="Asia/Tokyo" value="Asia/Tokyo" />
              <SelectItem text="Asia/Shanghai" value="Asia/Shanghai" />
            </Select>

            <NumberInput
              id="digest-hours-lookback"
              label={`Hours lookback (${data.hoursLookbackSource})`}
              min={1}
              max={168}
              value={hoursLookback}
              onChange={(_, state) => setHoursLookback(Number(state.value || hoursLookback))}
            />

            <NumberInput
              id="digest-max-posts"
              label={`Max posts per digest (${data.maxPostsPerDigestSource})`}
              min={1}
              max={100}
              value={maxPostsPerDigest}
              onChange={(_, state) => setMaxPostsPerDigest(Number(state.value || maxPostsPerDigest))}
            />

            <NumberInput
              id="digest-min-relevance"
              label={`Min relevance score (${data.minRelevanceScoreSource})`}
              min={0}
              max={1}
              step={0.05}
              value={minRelevanceScore}
              onChange={(_, state) => {
                const value = Number(state.value);
                if (Number.isFinite(value)) {
                  setMinRelevanceScore(Math.max(0, Math.min(1, value)));
                }
              }}
            />
          </div>
        )}

        <div className="form-actions">
          <Button disabled={saveMutation.isPending} onClick={() => saveMutation.mutate()}>
            Save Digest Preferences
          </Button>

          {saveMutation.isSuccess && (
            <InlineNotification
              kind="success"
              title="Preferences saved"
              subtitle="Digest settings were updated successfully."
              hideCloseButton
            />
          )}
        </div>
      </Tile>
    </div>
  );
}

function HistoryTab() {
  const [page, setPage] = useState(1);

  const historyQuery = useQuery({
    queryKey: ["digest-history", page],
    queryFn: () => fetchDigestHistory(HISTORY_PAGE_SIZE, (page - 1) * HISTORY_PAGE_SIZE),
  });

  const rows = useMemo(
    () =>
      (historyQuery.data?.deliveries ?? []).map((entry) => ({
        id: String(entry.id),
        deliveredAt: new Date(entry.deliveredAt).toLocaleString(),
        postCount: entry.postCount,
        channelCount: entry.channelCount,
        digestType: entry.digestType,
      })),
    [historyQuery.data?.deliveries],
  );

  const headers = [
    { key: "deliveredAt", header: "Delivered" },
    { key: "postCount", header: "Posts" },
    { key: "channelCount", header: "Channels" },
    { key: "digestType", header: "Type" },
  ];
  const isHistoryInitialLoading = historyQuery.isLoading && !historyQuery.data;

  return (
    <div className="page-section">
      <Tile>
        <h3>Digest history</h3>

        {isHistoryInitialLoading && <DataTableSkeleton columnCount={headers.length} rowCount={6} showToolbar={false} />}

        {historyQuery.error && (
          <InlineNotification
            kind="error"
            title="Failed to load digest history"
            subtitle={historyQuery.error instanceof Error ? historyQuery.error.message : "Unknown error"}
            hideCloseButton
          />
        )}

        {!isHistoryInitialLoading && (
          <DataTable rows={rows} headers={headers}>
            {({ rows, headers, getHeaderProps, getRowProps, getTableProps }) => (
              <TableContainer title="Digest deliveries">
                <Table {...getTableProps()}>
                  <TableHead>
                    <TableRow>
                      {headers.map((header) => (
                        <TableHeader {...getHeaderProps({ header })}>{header.header}</TableHeader>
                      ))}
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {rows.map((row) => (
                      <TableRow {...getRowProps({ row })}>
                        {row.cells.map((cell) => (
                          <TableCell key={cell.id}>{String(cell.value)}</TableCell>
                        ))}
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            )}
          </DataTable>
        )}

        {historyQuery.data && (
          <Pagination
            page={page}
            pageSize={HISTORY_PAGE_SIZE}
            pageSizes={[HISTORY_PAGE_SIZE]}
            totalItems={historyQuery.data.total}
            onChange={(event) => setPage(event.page)}
          />
        )}
      </Tile>
    </div>
  );
}

export default function DigestPage() {
  const { mode, user } = useAuth();
  const [selectedTabIndex, setSelectedTabIndex] = useState(0);

  return (
    <section className="page-section">
      <h1>Digest</h1>

      {mode !== "telegram-webapp" && <DigestUnavailableNotice />}

      {mode === "telegram-webapp" && (
        <Tabs selectedIndex={selectedTabIndex} onChange={({ selectedIndex }) => setSelectedTabIndex(selectedIndex)}>
          <TabList aria-label="Digest tabs" contained>
            <Tab>Channels</Tab>
            <Tab>Preferences</Tab>
            <Tab>History</Tab>
          </TabList>
          <TabPanels>
            <TabPanel>
              <ChannelsTab isOwner={Boolean(user?.isOwner)} isActive={selectedTabIndex === 0} />
            </TabPanel>
            <TabPanel>
              <PreferencesTab />
            </TabPanel>
            <TabPanel>
              <HistoryTab />
            </TabPanel>
          </TabPanels>
        </Tabs>
      )}
    </section>
  );
}
