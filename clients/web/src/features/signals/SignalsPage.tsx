import { useMemo, useState, type FormEvent } from "react";
import {
  BracketButton,
  BrutalistCard,
  MonoInput,
  MonoTextArea,
  SparkLoading,
  StatusBadge,
  Tag,
} from "../../design";
import type { SignalFeedbackAction, SignalSourceHealth, UserSignal } from "../../api/signals";
import {
  useSetSignalSourceActive,
  useSignalFeedback,
  useSignalHealth,
  useSignals,
  useSignalSourceHealth,
  useUpsertSignalTopic,
} from "../../hooks/useSignals";

const QUEUE_STATUSES = new Set(["candidate", "queued"]);

function formatScore(value: number | null | undefined): string {
  if (value == null) return "n/a";
  return `${Math.round(value * 100)}%`;
}

function formatDate(value: string | null | undefined): string {
  if (!value) return "Not scheduled";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function sourceLabel(source: SignalSourceHealth): string {
  return source.title || source.url || source.externalId || `${source.kind} source`;
}

function statusTone(status: string): "green" | "blue" | "warm-gray" | "gray" {
  if (status === "liked") return "green";
  if (status === "queued") return "blue";
  if (status === "dismissed" || status === "skipped" || status === "hidden_source") {
    return "warm-gray";
  }
  return "gray";
}

const sectionLabelStyle: React.CSSProperties = {
  fontFamily: "var(--frost-font-mono)",
  fontSize: "11px",
  fontWeight: 800,
  textTransform: "uppercase" as const,
  letterSpacing: "1px",
  color: "color-mix(in oklch, var(--frost-ink) 55%, transparent)",
  margin: 0,
};

const monoBodyStyle: React.CSSProperties = {
  fontFamily: "var(--frost-font-mono)",
  fontSize: "var(--frost-type-mono-body-size)",
  fontWeight: "var(--frost-type-mono-body-weight)" as React.CSSProperties["fontWeight"],
  color: "var(--frost-ink)",
  margin: 0,
};

const monoMetaStyle: React.CSSProperties = {
  fontFamily: "var(--frost-font-mono)",
  fontSize: "var(--frost-type-mono-body-size)",
  color: "color-mix(in oklch, var(--frost-ink) 60%, transparent)",
  margin: 0,
};

function SignalCard({
  signal,
  onFeedback,
  disabled,
}: {
  signal: UserSignal;
  onFeedback: (signalId: number, action: SignalFeedbackAction) => void;
  disabled: boolean;
}) {
  return (
    <BrutalistCard className="signal-card">
      <div className="signal-card__main">
        <div className="signal-card__meta" style={{ display: "flex", alignItems: "center", gap: "var(--frost-gap-row)", marginBottom: "var(--frost-gap-row)" }}>
          <Tag type={statusTone(signal.status)} size="sm">
            {signal.status}
          </Tag>
          <span style={monoMetaStyle}>{signal.sourceTitle || signal.sourceKind || "Unknown source"}</span>
          {signal.topicName ? <span style={monoMetaStyle}>{signal.topicName}</span> : null}
        </div>
        <h2
          style={{
            fontFamily: "var(--frost-font-mono)",
            fontSize: "var(--frost-type-mono-body-size)",
            fontWeight: 800,
            color: "var(--frost-ink)",
            margin: "0 0 var(--frost-gap-row)",
          }}
        >
          {signal.feedItemTitle || "Untitled signal"}
        </h2>
        {signal.feedItemUrl ? (
          <a
            className="signal-card__url"
            href={signal.feedItemUrl}
            target="_blank"
            rel="noreferrer"
            style={{
              fontFamily: "var(--frost-font-mono)",
              fontSize: "var(--frost-type-mono-body-size)",
              color: "var(--frost-ink)",
              textDecoration: "underline",
              textDecorationColor: "color-mix(in oklch, var(--frost-ink) 40%, transparent)",
              wordBreak: "break-all",
            }}
          >
            {signal.feedItemUrl}
          </a>
        ) : null}
      </div>
      <div className="signal-score" style={{ display: "flex", alignItems: "center", gap: "var(--frost-gap-row)", margin: "var(--frost-gap-row) 0" }}>
        <span style={sectionLabelStyle}>Score</span>
        <strong style={{ fontFamily: "var(--frost-font-mono)", fontWeight: 800, color: "var(--frost-ink)" }}>
          {formatScore(signal.finalScore)}
        </strong>
        <span style={monoMetaStyle}>{signal.filterStage || "heuristic"}</span>
      </div>
      <div
        className="signal-actions"
        aria-label={`Actions for ${signal.feedItemTitle || "signal"}`}
        style={{ display: "flex", gap: "var(--frost-gap-row)", flexWrap: "wrap" }}
      >
        <BracketButton size="sm" kind="primary" disabled={disabled} onClick={() => onFeedback(signal.id, "like")}>
          Like
        </BracketButton>
        <BracketButton size="sm" kind="secondary" disabled={disabled} onClick={() => onFeedback(signal.id, "queue")}>
          Queue
        </BracketButton>
        <BracketButton size="sm" kind="ghost" disabled={disabled} onClick={() => onFeedback(signal.id, "skip")}>
          Skip
        </BracketButton>
        <BracketButton size="sm" kind="danger--ghost" disabled={disabled} onClick={() => onFeedback(signal.id, "hide_source")}>
          Hide source
        </BracketButton>
      </div>
    </BrutalistCard>
  );
}

function SourceHealthRow({
  source,
  onToggle,
  disabled,
}: {
  source: SignalSourceHealth;
  onToggle: (sourceId: number, nextActive: boolean) => void;
  disabled: boolean;
}) {
  const hasErrors = source.fetchErrorCount > 0;
  return (
    <div
      className="source-health-row"
      style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "flex-start",
        padding: "var(--frost-gap-row) 0",
        borderBottom: "1px solid color-mix(in oklch, var(--frost-ink) 50%, transparent)",
      }}
    >
      <div>
        <div style={{ fontFamily: "var(--frost-font-mono)", fontWeight: 800, color: "var(--frost-ink)", marginBottom: "4px" }}>
          {sourceLabel(source)}
        </div>
        <div style={{ display: "flex", gap: "var(--frost-gap-row)" }}>
          <span style={monoMetaStyle}>{source.kind}</span>
          <span style={monoMetaStyle}>next: {formatDate(source.nextFetchAt)}</span>
        </div>
        {hasErrors ? (
          <p style={{ ...monoBodyStyle, color: "var(--frost-spark)", marginTop: "4px" }}>
            {source.lastError}
          </p>
        ) : null}
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: "var(--frost-gap-row)" }}>
        <Tag type={source.isActive ? "green" : "warm-gray"} size="sm">
          {source.isActive ? "active" : "paused"}
        </Tag>
        {hasErrors ? (
          <Tag type="red" size="sm">{source.fetchErrorCount} errors</Tag>
        ) : null}
        <BracketButton
          kind="ghost"
          size="sm"
          disabled={disabled}
          onClick={() => onToggle(source.id, !source.isActive)}
        >
          {source.isActive ? "Pause" : "Resume"}
        </BracketButton>
      </div>
    </div>
  );
}

function TopicForm() {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const mutation = useUpsertSignalTopic();

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) return;
    mutation.mutate(
      { name: trimmed, description: description.trim() || null, weight: 1 },
      {
        onSuccess: () => {
          setName("");
          setDescription("");
        },
      },
    );
  }

  return (
    <form
      className="topic-form"
      onSubmit={handleSubmit}
      style={{ display: "flex", flexDirection: "column", gap: "var(--frost-gap-section)" }}
    >
      <MonoInput
        id="signal-topic-name"
        labelText="Topic"
        value={name}
        onChange={(event) => setName(event.currentTarget.value)}
        placeholder="Local-first AI tooling"
      />
      <MonoTextArea
        id="signal-topic-description"
        labelText="Preference"
        value={description}
        onChange={(event) => setDescription(event.currentTarget.value)}
        placeholder="Prefer practical implementation notes over launch commentary."
      />
      <BracketButton type="submit" disabled={mutation.isPending || !name.trim()}>
        {mutation.isPending ? "Saving..." : "Save topic"}
      </BracketButton>
    </form>
  );
}

export default function SignalsPage() {
  const signalsQuery = useSignals();
  const healthQuery = useSignalHealth();
  const sourcesQuery = useSignalSourceHealth();
  const feedbackMutation = useSignalFeedback();
  const sourceToggleMutation = useSetSignalSourceActive();

  const queuedSignals = useMemo(
    () => (signalsQuery.data?.signals ?? []).filter((signal) => QUEUE_STATUSES.has(signal.status)),
    [signalsQuery.data?.signals],
  );
  const actedSignals = useMemo(
    () => (signalsQuery.data?.signals ?? []).filter((signal) => !QUEUE_STATUSES.has(signal.status)),
    [signalsQuery.data?.signals],
  );

  const chromaReady = healthQuery.data?.chroma.ready ?? true;
  const sourceRows = sourcesQuery.data?.sources ?? [];

  return (
    <main
      style={{
        maxWidth: "var(--frost-strip-7)",
        padding: "0 var(--frost-pad-page)",
        display: "flex",
        flexDirection: "column",
        gap: "var(--frost-gap-section)",
      }}
    >
      <div>
        <h1
          style={{
            fontFamily: "var(--frost-font-mono)",
            fontSize: "var(--frost-type-mono-emph-size)",
            fontWeight: "var(--frost-type-mono-emph-weight)" as React.CSSProperties["fontWeight"],
            letterSpacing: "var(--frost-type-mono-emph-tracking)",
            textTransform: "uppercase",
            color: "var(--frost-ink)",
            margin: "0 0 var(--frost-gap-row)",
          }}
        >
          Signals
        </h1>
        <p style={monoMetaStyle}>Ranked source items for the weekly triage loop.</p>
      </div>

      {healthQuery.isLoading ? <SparkLoading description="Checking signal health..." /> : null}

      {!chromaReady ? (
        <StatusBadge
          severity="info"
          title="Signal scoring is paused"
          subtitle="Chroma is required for personalization and similarity scoring."
        />
      ) : null}

      {signalsQuery.error ? (
        <StatusBadge
          severity="alarm"
          title="Signals could not load"
          subtitle={(signalsQuery.error as Error).message}
        />
      ) : null}

      {/* Health strip */}
      <div
        className="signal-health-strip"
        style={{ display: "flex", gap: "var(--frost-gap-row)" }}
      >
        <BrutalistCard style={{ flex: 1 }}>
          <span style={sectionLabelStyle}>Chroma</span>
          <strong style={{ display: "block", fontFamily: "var(--frost-font-mono)", fontWeight: 800, color: "var(--frost-ink)", marginTop: "4px" }}>
            {healthQuery.data?.chroma.ready ? "Ready" : "Unavailable"}
          </strong>
        </BrutalistCard>
        <BrutalistCard style={{ flex: 1 }}>
          <span style={sectionLabelStyle}>Sources</span>
          <strong style={{ display: "block", fontFamily: "var(--frost-font-mono)", fontWeight: 800, color: "var(--frost-ink)", marginTop: "4px" }}>
            {healthQuery.data?.sources.total ?? sourceRows.length}
          </strong>
        </BrutalistCard>
        <BrutalistCard style={{ flex: 1 }}>
          <span style={sectionLabelStyle}>Errored</span>
          <strong style={{ display: "block", fontFamily: "var(--frost-font-mono)", fontWeight: 800, color: "var(--frost-ink)", marginTop: "4px" }}>
            {healthQuery.data?.sources.errored ?? sourceRows.filter((row) => row.fetchErrorCount > 0).length}
          </strong>
        </BrutalistCard>
      </div>

      <div
        className="signal-layout"
        style={{ display: "flex", gap: "var(--frost-gap-page)", alignItems: "flex-start" }}
      >
        {/* Queue */}
        <div className="signal-queue" style={{ flex: 2, display: "flex", flexDirection: "column", gap: "var(--frost-gap-section)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "var(--frost-gap-row)" }}>
            <p style={sectionLabelStyle}>§ QUEUE</p>
            <Tag type="blue" size="sm">{queuedSignals.length}</Tag>
          </div>
          {signalsQuery.isLoading ? <SparkLoading description="Loading signals..." /> : null}
          {!signalsQuery.isLoading && queuedSignals.length === 0 ? (
            <BrutalistCard className="empty-panel">
              <h3
                style={{
                  fontFamily: "var(--frost-font-mono)",
                  fontWeight: 800,
                  textTransform: "uppercase",
                  letterSpacing: "1px",
                  color: "var(--frost-ink)",
                  margin: "0 0 var(--frost-gap-row)",
                }}
              >
                No queued signals
              </h3>
              <p style={monoMetaStyle}>
                New items appear here after RSS or Telegram channel ingestion runs.
              </p>
            </BrutalistCard>
          ) : null}
          <div className="signal-card-list" style={{ display: "flex", flexDirection: "column", gap: "var(--frost-gap-section)" }}>
            {queuedSignals.map((signal) => (
              <SignalCard
                key={signal.id}
                signal={signal}
                disabled={feedbackMutation.isPending}
                onFeedback={(signalId, action) => feedbackMutation.mutate({ signalId, action })}
              />
            ))}
          </div>
        </div>

        {/* Sidebar */}
        <aside className="signal-sidebar" style={{ flex: 1, display: "flex", flexDirection: "column", gap: "var(--frost-gap-section)" }}>
          <BrutalistCard className="signal-panel">
            <p style={{ ...sectionLabelStyle, marginBottom: "var(--frost-gap-section)" }}>§ TOPICS</p>
            <TopicForm />
          </BrutalistCard>

          <BrutalistCard className="signal-panel">
            <div style={{ display: "flex", alignItems: "center", gap: "var(--frost-gap-row)", marginBottom: "var(--frost-gap-section)" }}>
              <p style={sectionLabelStyle}>§ SOURCES</p>
              <Tag type="gray" size="sm">{sourceRows.length}</Tag>
            </div>
            {sourcesQuery.isLoading ? <SparkLoading description="Loading sources..." /> : null}
            {sourceRows.length === 0 && !sourcesQuery.isLoading ? (
              <p style={monoMetaStyle}>No signal sources are subscribed yet.</p>
            ) : null}
            <div className="source-health-list">
              {sourceRows.map((source) => (
                <SourceHealthRow
                  key={source.id}
                  source={source}
                  disabled={sourceToggleMutation.isPending}
                  onToggle={(sourceId, isActive) =>
                    sourceToggleMutation.mutate({ sourceId, isActive })
                  }
                />
              ))}
            </div>
          </BrutalistCard>
        </aside>
      </div>

      {actedSignals.length > 0 ? (
        <section className="signal-history" style={{ display: "flex", flexDirection: "column", gap: "var(--frost-gap-section)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "var(--frost-gap-row)" }}>
            <p style={sectionLabelStyle}>§ RECENT DECISIONS</p>
            <Tag type="gray" size="sm">{actedSignals.length}</Tag>
          </div>
          <div
            className="signal-history-list"
            style={{
              border: "1px solid color-mix(in oklch, var(--frost-ink) 50%, transparent)",
              display: "flex",
              flexDirection: "column",
            }}
          >
            {actedSignals.slice(0, 8).map((signal) => (
              <div
                key={signal.id}
                className="signal-history-row"
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  padding: "12px 16px",
                  borderBottom: "1px solid color-mix(in oklch, var(--frost-ink) 50%, transparent)",
                }}
              >
                <span style={monoBodyStyle}>{signal.feedItemTitle || "Untitled signal"}</span>
                <Tag type={statusTone(signal.status)} size="sm">{signal.status}</Tag>
              </div>
            ))}
          </div>
        </section>
      ) : null}
    </main>
  );
}
