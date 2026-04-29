import { useState } from "react";
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
import { QueryErrorNotification } from "../../components/QueryErrorNotification";
import { useClearCache, useMetrics } from "../../hooks/useAdmin";

export default function AdminMetrics() {
  const [cacheMessage, setCacheMessage] = useState<{ kind: "success" | "error"; text: string } | null>(null);
  const { data, isLoading, error } = useMetrics();
  const cacheMutation = useClearCache(
    (result) => setCacheMessage({ kind: "success", text: `Cleared ${result.clearedKeys} cached key(s).` }),
    (err) => setCacheMessage({ kind: "error", text: err instanceof Error ? err.message : "Failed to clear cache" }),
  );

  if (isLoading) return <SkeletonText paragraph lineCount={6} />;

  const db = data?.database;
  const llm = data?.llm7d;
  const scraper = data?.scraper7d;

  const totalRows = db
    ? Object.values(db.tableCounts).reduce((sum, count) => sum + Math.max(0, count), 0)
    : 0;

  return (
    <>
      <QueryErrorNotification error={error} title="Failed to load metrics" />

      {db && (
        <Tile style={{ marginBottom: "1rem" }}>
          <h4>Database</h4>
          <p>
            <strong>Path:</strong> {db.dbPath}
          </p>
          <p>
            <strong>File size:</strong> {db.fileSizeMb} MB &nbsp;|&nbsp;
            <strong>Total rows:</strong> {totalRows.toLocaleString()} &nbsp;|&nbsp;
            <strong>Tables:</strong> {Object.keys(db.tableCounts).length}
          </p>

          <StructuredListWrapper>
            <StructuredListHead>
              <StructuredListRow head>
                <StructuredListCell head>Table</StructuredListCell>
                <StructuredListCell head>Rows</StructuredListCell>
              </StructuredListRow>
            </StructuredListHead>
            <StructuredListBody>
              {Object.entries(db.tableCounts).map(([table, count]) => (
                <StructuredListRow key={table}>
                  <StructuredListCell>{table}</StructuredListCell>
                  <StructuredListCell>{count >= 0 ? count.toLocaleString() : "error"}</StructuredListCell>
                </StructuredListRow>
              ))}
            </StructuredListBody>
          </StructuredListWrapper>
        </Tile>
      )}

      {llm && (
        <Tile style={{ marginBottom: "1rem" }}>
          <h4>LLM (last 7 days)</h4>
          <div style={{ display: "flex", gap: "2rem", flexWrap: "wrap", marginTop: "0.5rem" }}>
            <div>
              <p className="cds--label">Total Calls</p>
              <p style={{ fontSize: "1.25rem", fontWeight: 600 }}>{llm.totalCalls.toLocaleString()}</p>
            </div>
            <div>
              <p className="cds--label">Avg Latency</p>
              <p style={{ fontSize: "1.25rem", fontWeight: 600 }}>{llm.avgLatencyMs.toLocaleString()} ms</p>
            </div>
            <div>
              <p className="cds--label">Prompt Tokens</p>
              <p style={{ fontSize: "1.25rem", fontWeight: 600 }}>{llm.totalPromptTokens.toLocaleString()}</p>
            </div>
            <div>
              <p className="cds--label">Completion Tokens</p>
              <p style={{ fontSize: "1.25rem", fontWeight: 600 }}>{llm.totalCompletionTokens.toLocaleString()}</p>
            </div>
            <div>
              <p className="cds--label">Total Cost</p>
              <p style={{ fontSize: "1.25rem", fontWeight: 600 }}>${llm.totalCostUsd.toFixed(4)}</p>
            </div>
            <div>
              <p className="cds--label">Error Rate</p>
              <p style={{ fontSize: "1.25rem", fontWeight: 600, color: llm.errorRate > 0.05 ? "var(--rtk-color-support-error, var(--cds-support-error))" : undefined }}>
                {(llm.errorRate * 100).toFixed(2)}%
              </p>
            </div>
          </div>
        </Tile>
      )}

      {scraper && Object.keys(scraper).length > 0 && (
        <Tile style={{ marginBottom: "1rem" }}>
          <h4>Scraper (last 7 days)</h4>
          <StructuredListWrapper>
            <StructuredListHead>
              <StructuredListRow head>
                <StructuredListCell head>Provider</StructuredListCell>
                <StructuredListCell head>Total</StructuredListCell>
                <StructuredListCell head>Success</StructuredListCell>
                <StructuredListCell head>Success Rate</StructuredListCell>
              </StructuredListRow>
            </StructuredListHead>
            <StructuredListBody>
              {Object.entries(scraper).map(([provider, stats]) => (
                <StructuredListRow key={provider}>
                  <StructuredListCell>{provider}</StructuredListCell>
                  <StructuredListCell>{stats.total.toLocaleString()}</StructuredListCell>
                  <StructuredListCell>{stats.success.toLocaleString()}</StructuredListCell>
                  <StructuredListCell>{(stats.successRate * 100).toFixed(1)}%</StructuredListCell>
                </StructuredListRow>
              ))}
            </StructuredListBody>
          </StructuredListWrapper>
        </Tile>
      )}

      <Tile>
        <h4>Cache</h4>
        <p>Clear the Redis URL cache. This forces fresh content extraction on the next request.</p>

        <Button
          kind="danger"
          onClick={() => {
            setCacheMessage(null);
            cacheMutation.mutate();
          }}
          disabled={cacheMutation.isPending}
        >
          {cacheMutation.isPending ? "Clearing..." : "Clear URL Cache"}
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
    </>
  );
}
