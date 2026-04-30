import React, { useCallback, useMemo, useState } from "react";
import {
  Button,
  DataTableSkeleton,
  FileUploader,
  InlineNotification,
  Link,
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
} from "../../design/table/BrutalistTable";
import { exportOPML } from "../../api/rss";
import type { RSSFeedItem } from "../../api/rss";
import {
  useFeedItems,
  useImportOPML,
  useRSSSubscriptions,
  useRefreshFeed,
  useSubscribeToFeed,
  useUnsubscribeFromFeed,
} from "../../hooks/useRSS";

function resolveSubstackFeedUrl(name: string): string {
  const trimmed = name.trim();
  if (!trimmed) return "";
  if (!trimmed.includes("/") && !trimmed.includes(".")) {
    return `https://${trimmed}.substack.com/feed`;
  }
  const url = trimmed.startsWith("http") ? trimmed : `https://${trimmed}`;
  if (url.includes("substack.com") && !url.endsWith("/feed")) {
    try {
      const parsed = new URL(url);
      return `${parsed.protocol}//${parsed.hostname}/feed`;
    } catch {
      return url;
    }
  }
  return url;
}

function FeedItemsPreview({ feedId }: { feedId: number }) {
  const { data, isLoading } = useFeedItems(feedId);

  if (isLoading) return <p>Loading items...</p>;
  if (!data?.items?.length) return <p>No items yet.</p>;

  return (
    <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
      {data.items.slice(0, 10).map((item: RSSFeedItem) => (
        <li key={item.id} style={{ marginBottom: "0.5rem" }}>
          {item.url ? (
            <Link href={item.url} target="_blank" rel="noopener noreferrer">
              {item.title || item.url}
            </Link>
          ) : (
            <span>{item.title || "(untitled)"}</span>
          )}
          {item.publishedAt && (
            <span className="muted" style={{ marginLeft: "0.5rem" }}>
              {new Date(item.publishedAt).toLocaleDateString()}
            </span>
          )}
        </li>
      ))}
    </ul>
  );
}

export function RSSFeedsTab() {
  const [feedUrl, setFeedUrl] = useState("");
  const [substackName, setSubstackName] = useState("");
  const [confirmUnsubId, setConfirmUnsubId] = useState<number | null>(null);

  const subscriptionsQuery = useRSSSubscriptions();
  const subscribeMutation = useSubscribeToFeed();
  const unsubscribeMutation = useUnsubscribeFromFeed();
  const refreshMutation = useRefreshFeed();
  const importMutation = useImportOPML();

  const isInitialLoading = subscriptionsQuery.isLoading && !subscriptionsQuery.data;

  const headers = [
    { key: "title", header: "Title" },
    { key: "url", header: "URL" },
    { key: "status", header: "Status" },
    { key: "actions", header: "Actions" },
  ];

  const subscriptions = useMemo(
    () => subscriptionsQuery.data?.feeds ?? [],
    [subscriptionsQuery.data],
  );

  const rows = useMemo(
    () =>
      subscriptions.map((sub) => ({
        id: String(sub.subscriptionId),
        title: sub.feedTitle ?? "-",
        url: sub.feedUrl,
        status: sub.isActive ? "Active" : "Inactive",
        actions: sub,
      })),
    [subscriptions],
  );

  const feedIdLookup = useMemo(() => {
    const map = new Map<string, number>();
    for (const sub of subscriptions) {
      map.set(String(sub.subscriptionId), sub.feedId);
    }
    return map;
  }, [subscriptions]);

  const handleSubscribe = useCallback(() => {
    const trimmed = feedUrl.trim();
    if (!trimmed) return;
    subscribeMutation.mutate({ url: trimmed }, { onSuccess: () => setFeedUrl("") });
  }, [feedUrl, subscribeMutation]);

  const handleSubstackSubscribe = useCallback(() => {
    const resolved = resolveSubstackFeedUrl(substackName);
    if (!resolved) return;
    subscribeMutation.mutate({ url: resolved }, { onSuccess: () => setSubstackName("") });
  }, [substackName, subscribeMutation]);

  const handleUnsubscribe = useCallback(
    (subscriptionId: number) => {
      if (confirmUnsubId === subscriptionId) {
        unsubscribeMutation.mutate(subscriptionId, {
          onSuccess: () => setConfirmUnsubId(null),
        });
      } else {
        setConfirmUnsubId(subscriptionId);
      }
    },
    [confirmUnsubId, unsubscribeMutation],
  );

  const handleExportOPML = useCallback(async () => {
    try {
      const blob = await exportOPML();
      const url = URL.createObjectURL(blob instanceof Blob ? blob : new Blob([JSON.stringify(blob)], { type: "text/xml" }));
      const a = document.createElement("a");
      a.href = url;
      a.download = "feeds.opml";
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      // Error handled silently; user can retry
    }
  }, []);

  const handleImportOPML = useCallback(
    (event: React.SyntheticEvent<HTMLElement>) => {
      const input = event.target as HTMLInputElement;
      const file = input.files?.[0];
      if (file) {
        importMutation.mutate(file);
      }
    },
    [importMutation],
  );

  const anyError =
    subscriptionsQuery.error ||
    subscribeMutation.error ||
    unsubscribeMutation.error ||
    refreshMutation.error ||
    importMutation.error;

  return (
    <div className="page-section">
      <Tile>
        <h3>RSS Feed Subscriptions</h3>

        <div style={{ display: "flex", gap: "1rem", marginBottom: "1rem", flexWrap: "wrap" }}>
          <div style={{ flex: "1 1 300px" }}>
            <TextInput
              id="substack-name"
              labelText="Substack"
              placeholder="Publication name (e.g. platformer)"
              value={substackName}
              onChange={(e) => setSubstackName(e.currentTarget.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") handleSubstackSubscribe();
              }}
            />
            <Button
              kind="secondary"
              size="sm"
              disabled={!substackName.trim() || subscribeMutation.isPending}
              onClick={handleSubstackSubscribe}
              style={{ marginTop: "0.5rem" }}
            >
              Add Substack
            </Button>
          </div>
          <div style={{ flex: "1 1 300px" }}>
            <TextInput
              id="rss-feed-url"
              labelText="Feed URL"
              placeholder="https://example.com/feed.xml"
              value={feedUrl}
              onChange={(e) => setFeedUrl(e.currentTarget.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") handleSubscribe();
              }}
            />
            <Button
              kind="primary"
              size="sm"
              disabled={!feedUrl.trim() || subscribeMutation.isPending}
              onClick={handleSubscribe}
              style={{ marginTop: "0.5rem" }}
            >
              Add Feed
            </Button>
          </div>
        </div>

        {anyError && (
          <InlineNotification
            kind="error"
            title="RSS operation failed"
            subtitle={(anyError as Error)?.message ?? "Unknown error"}
            hideCloseButton
          />
        )}

        {subscribeMutation.isSuccess && (
          <InlineNotification
            kind="success"
            title="Feed subscribed"
            hideCloseButton
          />
        )}

        {importMutation.isSuccess && (
          <InlineNotification
            kind="success"
            title="OPML imported"
            subtitle={`Imported: ${importMutation.data.imported}, Errors: ${importMutation.data.errors}`}
            hideCloseButton
          />
        )}

        {isInitialLoading && (
          <DataTableSkeleton columnCount={headers.length} rowCount={4} showToolbar={false} />
        )}

        {!isInitialLoading && subscriptions.length === 0 && !subscriptionsQuery.error && (
          <p className="page-subtitle" style={{ marginTop: "1rem" }}>
            No feed subscriptions yet. Add a Substack or RSS feed URL above to get started.
          </p>
        )}

        {!isInitialLoading && subscriptions.length > 0 && (
          <BrutalistTable rows={rows} headers={headers} isSortable={false}>
            {({ rows, headers, getHeaderProps, getRowProps, getTableProps, getTableContainerProps, getExpandedRowProps }) => (
              <TableContainer title="Subscribed feeds" {...getTableContainerProps()}>
                {/* Frost-styled toolbar */}
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "flex-end",
                    padding: "8px 16px",
                    borderBottom: "1px solid color-mix(in oklch, var(--frost-ink) 50%, transparent)",
                    backgroundColor: "var(--frost-page)",
                    gap: "8px",
                  }}
                >
                  <Button kind="ghost" size="sm" onClick={handleExportOPML}>
                    Export OPML
                  </Button>
                  <FileUploader
                    accept={[".opml", ".xml"]}
                    buttonLabel="Import OPML"
                    buttonKind="ghost"
                    size="sm"
                    filenameStatus="complete"
                    onChange={handleImportOPML}
                    disabled={importMutation.isPending}
                  />
                </div>
                <Table {...getTableProps()}>
                  <TableHead>
                    <TableRow>
                      <TableExpandHeaderCell />
                      {headers.map((header) => (
                        <TableHeader key={header.key} {...getHeaderProps({ header })}>{header.header}</TableHeader>
                      ))}
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {rows.map((row) => {
                      const subId = Number(row.id);
                      const feedId = feedIdLookup.get(row.id) ?? 0;
                      const expandedProps = getExpandedRowProps({ row });
                      const rowProps = getRowProps({ row });
                      return (
                        <React.Fragment key={row.id}>
                          <TableRow {...rowProps}>
                            <TableExpandCell
                              isExpanded={row.isExpanded ?? false}
                              onToggle={expandedProps.onToggle as () => void}
                            />
                            {row.cells.map((cell) => {
                              if (cell.info.header === "actions") {
                                return (
                                  <TableCell key={cell.id}>
                                    <Button
                                      kind="ghost"
                                      size="sm"
                                      disabled={refreshMutation.isPending}
                                      onClick={() => refreshMutation.mutate(feedId)}
                                      style={{ marginRight: "0.5rem" }}
                                    >
                                      Refresh
                                    </Button>
                                    <Button
                                      kind={confirmUnsubId === subId ? "danger" : "danger--ghost"}
                                      size="sm"
                                      disabled={unsubscribeMutation.isPending}
                                      onClick={() => handleUnsubscribe(subId)}
                                    >
                                      {confirmUnsubId === subId ? "Confirm" : "Unsubscribe"}
                                    </Button>
                                  </TableCell>
                                );
                              }
                              return <TableCell key={cell.id}>{String(cell.value)}</TableCell>;
                            })}
                          </TableRow>
                          {row.isExpanded && (
                            <TableRow>
                              <TableCell
                                colSpan={headers.length + 1}
                                style={{ padding: "16px" }}
                              >
                                <FeedItemsPreview feedId={feedId} />
                              </TableCell>
                            </TableRow>
                          )}
                        </React.Fragment>
                      );
                    })}
                  </TableBody>
                </Table>
              </TableContainer>
            )}
          </BrutalistTable>
        )}
      </Tile>
    </div>
  );
}
