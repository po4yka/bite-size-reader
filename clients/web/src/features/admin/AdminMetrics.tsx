import { useState } from "react";
import {
  BracketButton,
  BrutalistCard,
  BrutalistSkeletonText,
  RowDigestBody,
  RowDigestCell,
  RowDigestHead,
  RowDigestRow,
  RowDigestWrapper,
  StatusBadge,
} from "../../design";
import { QueryErrorNotification } from "../../components/QueryErrorNotification";
import { useClearCache, useMetrics } from "../../hooks/useAdmin";

export default function AdminMetrics() {
  const [cacheMessage, setCacheMessage] = useState<{ kind: "success" | "error"; text: string } | null>(null);
  const { data, isLoading, error } = useMetrics();
  const cacheMutation = useClearCache(
    (result) => setCacheMessage({ kind: "success", text: `Cleared ${result.clearedKeys} cached key(s).` }),
    (err) => setCacheMessage({ kind: "error", text: err instanceof Error ? err.message : "Failed to clear cache" }),
  );

  if (isLoading) return <BrutalistSkeletonText paragraph lineCount={6} />;

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
        <BrutalistCard style={{ marginBottom: "1rem" }}>
          <p
            style={{
              fontFamily: "var(--frost-font-mono)",
              fontSize: "11px",
              fontWeight: 800,
              textTransform: "uppercase",
              letterSpacing: "1px",
              color: "color-mix(in oklch, var(--frost-ink) 55%, transparent)",
              marginBottom: "0.75rem",
            }}
          >
            § Database
          </p>
          <p>
            <strong>Path:</strong> {db.dbPath}
          </p>
          <p>
            <strong>File size:</strong> {db.fileSizeMb} MB &nbsp;|&nbsp;
            <strong>Total rows:</strong> {totalRows.toLocaleString()} &nbsp;|&nbsp;
            <strong>Tables:</strong> {Object.keys(db.tableCounts).length}
          </p>

          <RowDigestWrapper>
            <RowDigestHead>
              <RowDigestRow head>
                <RowDigestCell head>Table</RowDigestCell>
                <RowDigestCell head>Rows</RowDigestCell>
              </RowDigestRow>
            </RowDigestHead>
            <RowDigestBody>
              {Object.entries(db.tableCounts).map(([table, count]) => (
                <RowDigestRow key={table}>
                  <RowDigestCell>{table}</RowDigestCell>
                  <RowDigestCell>{count >= 0 ? count.toLocaleString() : "error"}</RowDigestCell>
                </RowDigestRow>
              ))}
            </RowDigestBody>
          </RowDigestWrapper>
        </BrutalistCard>
      )}

      {llm && (
        <BrutalistCard style={{ marginBottom: "1rem" }}>
          <p
            style={{
              fontFamily: "var(--frost-font-mono)",
              fontSize: "11px",
              fontWeight: 800,
              textTransform: "uppercase",
              letterSpacing: "1px",
              color: "color-mix(in oklch, var(--frost-ink) 55%, transparent)",
              marginBottom: "0.75rem",
            }}
          >
            § LLM (last 7 days)
          </p>
          <div style={{ display: "flex", gap: "2rem", flexWrap: "wrap", marginTop: "0.5rem" }}>
            <div>
              <p className="rtk-label">Total Calls</p>
              <p style={{ fontSize: "1.25rem", fontWeight: 600 }}>{llm.totalCalls.toLocaleString()}</p>
            </div>
            <div>
              <p className="rtk-label">Avg Latency</p>
              <p style={{ fontSize: "1.25rem", fontWeight: 600 }}>{llm.avgLatencyMs.toLocaleString()} ms</p>
            </div>
            <div>
              <p className="rtk-label">Prompt Tokens</p>
              <p style={{ fontSize: "1.25rem", fontWeight: 600 }}>{llm.totalPromptTokens.toLocaleString()}</p>
            </div>
            <div>
              <p className="rtk-label">Completion Tokens</p>
              <p style={{ fontSize: "1.25rem", fontWeight: 600 }}>{llm.totalCompletionTokens.toLocaleString()}</p>
            </div>
            <div>
              <p className="rtk-label">Total Cost</p>
              <p style={{ fontSize: "1.25rem", fontWeight: 600 }}>${llm.totalCostUsd.toFixed(4)}</p>
            </div>
            <div>
              <p className="rtk-label">Error Rate</p>
              <p
                style={{
                  fontSize: "1.25rem",
                  fontWeight: 600,
                  color: llm.errorRate > 0.05
                    ? "var(--frost-spark)"
                    : undefined,
                }}
              >
                {(llm.errorRate * 100).toFixed(2)}%
              </p>
            </div>
          </div>
        </BrutalistCard>
      )}

      {scraper && Object.keys(scraper).length > 0 && (
        <BrutalistCard style={{ marginBottom: "1rem" }}>
          <p
            style={{
              fontFamily: "var(--frost-font-mono)",
              fontSize: "11px",
              fontWeight: 800,
              textTransform: "uppercase",
              letterSpacing: "1px",
              color: "color-mix(in oklch, var(--frost-ink) 55%, transparent)",
              marginBottom: "0.75rem",
            }}
          >
            § Scraper (last 7 days)
          </p>
          <RowDigestWrapper>
            <RowDigestHead>
              <RowDigestRow head>
                <RowDigestCell head>Provider</RowDigestCell>
                <RowDigestCell head>Total</RowDigestCell>
                <RowDigestCell head>Success</RowDigestCell>
                <RowDigestCell head>Success Rate</RowDigestCell>
              </RowDigestRow>
            </RowDigestHead>
            <RowDigestBody>
              {Object.entries(scraper).map(([provider, stats]) => (
                <RowDigestRow key={provider}>
                  <RowDigestCell>{provider}</RowDigestCell>
                  <RowDigestCell>{stats.total.toLocaleString()}</RowDigestCell>
                  <RowDigestCell>{stats.success.toLocaleString()}</RowDigestCell>
                  <RowDigestCell>{(stats.successRate * 100).toFixed(1)}%</RowDigestCell>
                </RowDigestRow>
              ))}
            </RowDigestBody>
          </RowDigestWrapper>
        </BrutalistCard>
      )}

      <BrutalistCard>
        <p
          style={{
            fontFamily: "var(--frost-font-mono)",
            fontSize: "11px",
            fontWeight: 800,
            textTransform: "uppercase",
            letterSpacing: "1px",
            color: "color-mix(in oklch, var(--frost-ink) 55%, transparent)",
            marginBottom: "0.75rem",
          }}
        >
          § Cache
        </p>
        <p>Clear the Redis URL cache. This forces fresh content extraction on the next request.</p>

        <BracketButton
          kind="danger"
          onClick={() => {
            setCacheMessage(null);
            cacheMutation.mutate();
          }}
          disabled={cacheMutation.isPending}
        >
          {cacheMutation.isPending ? "Clearing..." : "Clear URL Cache"}
        </BracketButton>

        {cacheMessage && (
          <div className="digest-inline-margin-top">
            <StatusBadge
              severity={cacheMessage.kind === "success" ? "info" : "alarm"}
              title={cacheMessage.kind === "success" ? "Cache cleared ✓" : "Error"}
              dismissible
              onDismiss={() => setCacheMessage(null)}
            >
              {cacheMessage.text}
            </StatusBadge>
          </div>
        )}
      </BrutalistCard>
    </>
  );
}
