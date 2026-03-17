import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  Button,
  InlineNotification,
  SkeletonText,
  StructuredListBody,
  StructuredListCell,
  StructuredListHead,
  StructuredListRow,
  StructuredListWrapper,
  Tile,
} from "@carbon/react";
import { clearCache, fetchDbInfo } from "../../api/admin";

export default function AdminPage() {
  const [cacheMessage, setCacheMessage] = useState<{ kind: "success" | "error"; text: string } | null>(null);

  const dbQuery = useQuery({
    queryKey: ["admin-db-info"],
    queryFn: () => fetchDbInfo(),
  });

  const cacheMutation = useMutation({
    mutationFn: () => clearCache(),
    onSuccess: (result) => {
      setCacheMessage({ kind: "success", text: `Cleared ${result.clearedKeys} cached key(s).` });
    },
    onError: (err) => {
      setCacheMessage({ kind: "error", text: err instanceof Error ? err.message : "Failed to clear cache" });
    },
  });

  const totalRows = dbQuery.data
    ? Object.values(dbQuery.data.tableCounts).reduce((sum, count) => sum + Math.max(0, count), 0)
    : 0;

  return (
    <section className="page-section">
      <h1>Admin</h1>

      <Tile>
        <h3>Database</h3>

        {dbQuery.isLoading && !dbQuery.data && (
          <>
            <SkeletonText paragraph lineCount={3} />
          </>
        )}

        {dbQuery.error && (
          <InlineNotification
            kind="error"
            title="Failed to load DB info"
            subtitle={dbQuery.error instanceof Error ? dbQuery.error.message : "Unknown error"}
            hideCloseButton
          />
        )}

        {dbQuery.data && (
          <>
            <p>
              <strong>Path:</strong> {dbQuery.data.dbPath}
            </p>
            <p>
              <strong>File size:</strong> {dbQuery.data.fileSizeMb} MB &nbsp;|&nbsp;
              <strong>Total rows:</strong> {totalRows.toLocaleString()} &nbsp;|&nbsp;
              <strong>Tables:</strong> {Object.keys(dbQuery.data.tableCounts).length}
            </p>

            <StructuredListWrapper>
              <StructuredListHead>
                <StructuredListRow head>
                  <StructuredListCell head>Table</StructuredListCell>
                  <StructuredListCell head>Rows</StructuredListCell>
                </StructuredListRow>
              </StructuredListHead>
              <StructuredListBody>
                {Object.entries(dbQuery.data.tableCounts).map(([table, count]) => (
                  <StructuredListRow key={table}>
                    <StructuredListCell>{table}</StructuredListCell>
                    <StructuredListCell>{count >= 0 ? count.toLocaleString() : "error"}</StructuredListCell>
                  </StructuredListRow>
                ))}
              </StructuredListBody>
            </StructuredListWrapper>
          </>
        )}
      </Tile>

      <Tile>
        <h3>Cache</h3>
        <p>Clear the Redis URL cache. This forces fresh content extraction on the next request.</p>

        <Button
          kind="danger"
          onClick={() => {
            setCacheMessage(null);
            cacheMutation.mutate();
          }}
          disabled={cacheMutation.isPending}
        >
          {cacheMutation.isPending ? "Clearing…" : "Clear URL Cache"}
        </Button>

        {cacheMessage && (
          <div className="digest-inline-margin-top">
            <InlineNotification
              kind={cacheMessage.kind}
              title={cacheMessage.kind === "success" ? "Cache cleared" : "Error"}
              subtitle={cacheMessage.text}
              onCloseButtonClick={() => setCacheMessage(null)}
            />
          </div>
        )}
      </Tile>
    </section>
  );
}
