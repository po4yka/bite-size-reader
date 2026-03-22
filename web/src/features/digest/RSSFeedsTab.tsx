import React, { useCallback, useMemo, useState } from "react";
import {
  Button,
  DataTable,
  DataTableSkeleton,
  FileUploader,
  InlineNotification,
  Link,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableExpandHeader,
  TableExpandRow,
  TableExpandedRow,
  TableHead,
  TableHeader,
  TableRow,
  TableToolbar,
  TableToolbarContent,
  TextInput,
  Tile,
} from "@carbon/react";
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
    { key: "lastFetched", header: "Last Fetched" },
    { key: "errors", header: "Errors" },
    { key: "status", header: "Status" },
    { key: "actions", header: "Actions" },
  ];

  const subscriptions = useMemo(
    () => subscriptionsQuery.data?.subscriptions ?? [],
    [subscriptionsQuery.data],
  );

  const rows = useMemo(
    () =>
      subscriptions.map((sub) => ({
        id: String(sub.id),
        title: sub.feed.title ?? "-",
        url: sub.feed.url,
        lastFetched: sub.feed.lastFetchedAt
          ? new Date(sub.feed.lastFetchedAt).toLocaleString()
          : "Never",
        errors: sub.feed.fetchErrorCount,
        status: sub.feed.isActive ? "Active" : "Inactive",
        actions: sub,
      })),
    [subscriptions],
  );

  const feedIdLookup = useMemo(() => {
    const map = new Map<string, number>();
    for (const sub of subscriptions) {
      map.set(String(sub.id), sub.feedId);
    }
    return map;
  }, [subscriptions]);

  const handleSubscribe = useCallback(() => {
    const trimmed = feedUrl.trim();
    if (!trimmed) return;
    subscribeMutation.mutate({ url: trimmed }, { onSuccess: () => setFeedUrl("") });
  }, [feedUrl, subscribeMutation]);

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

        <div className="form-actions" style={{ marginBottom: "1rem" }}>
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
          >
            Add Feed
          </Button>
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

        {!isInitialLoading && (
          <DataTable rows={rows} headers={headers} isSortable={false}>
            {({ rows, headers, getHeaderProps, getRowProps, getTableProps, getTableContainerProps }) => (
              <TableContainer title="Subscribed feeds" {...getTableContainerProps()}>
                <TableToolbar>
                  <TableToolbarContent>
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
                  </TableToolbarContent>
                </TableToolbar>
                <Table {...getTableProps()}>
                  <TableHead>
                    <TableRow>
                      <TableExpandHeader />
                      {headers.map((header) => (
                        <TableHeader {...getHeaderProps({ header })}>{header.header}</TableHeader>
                      ))}
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {rows.map((row) => {
                      const subId = Number(row.id);
                      const feedId = feedIdLookup.get(row.id) ?? 0;
                      return (
                        <React.Fragment key={row.id}>
                          <TableExpandRow {...getRowProps({ row })}>
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
                          </TableExpandRow>
                          <TableExpandedRow colSpan={headers.length + 1}>
                            <FeedItemsPreview feedId={feedId} />
                          </TableExpandedRow>
                        </React.Fragment>
                      );
                    })}
                  </TableBody>
                </Table>
              </TableContainer>
            )}
          </DataTable>
        )}
      </Tile>
    </div>
  );
}
