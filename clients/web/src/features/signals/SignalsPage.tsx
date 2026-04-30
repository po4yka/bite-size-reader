import { useMemo, useState, type FormEvent } from "react";
import { Button, InlineLoading, InlineNotification, Tag, TextArea, TextInput, Tile } from "../../design";
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
    <Tile className="signal-card">
      <div className="signal-card__main">
        <div className="signal-card__meta">
          <Tag type={statusTone(signal.status)} size="sm">
            {signal.status}
          </Tag>
          <span>{signal.sourceTitle || signal.sourceKind || "Unknown source"}</span>
          {signal.topicName ? <span>{signal.topicName}</span> : null}
        </div>
        <h2>{signal.feedItemTitle || "Untitled signal"}</h2>
        {signal.feedItemUrl ? (
          <a className="signal-card__url" href={signal.feedItemUrl} target="_blank" rel="noreferrer">
            {signal.feedItemUrl}
          </a>
        ) : null}
      </div>
      <div className="signal-score">
        <span className="rtk-label">Score</span>
        <strong>{formatScore(signal.finalScore)}</strong>
        <span>{signal.filterStage || "heuristic"}</span>
      </div>
      <div className="signal-actions" aria-label={`Actions for ${signal.feedItemTitle || "signal"}`}>
        <Button size="sm" kind="primary" disabled={disabled} onClick={() => onFeedback(signal.id, "like")}>
          Like
        </Button>
        <Button size="sm" kind="secondary" disabled={disabled} onClick={() => onFeedback(signal.id, "queue")}>
          Queue
        </Button>
        <Button size="sm" kind="ghost" disabled={disabled} onClick={() => onFeedback(signal.id, "skip")}>
          Skip
        </Button>
        <Button size="sm" kind="danger--ghost" disabled={disabled} onClick={() => onFeedback(signal.id, "hide_source")}>
          Hide source
        </Button>
      </div>
    </Tile>
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
    <div className="source-health-row">
      <div>
        <div className="source-health-row__title">{sourceLabel(source)}</div>
        <div className="source-health-row__meta">
          <span>{source.kind}</span>
          <span>next: {formatDate(source.nextFetchAt)}</span>
        </div>
        {hasErrors ? <p className="source-health-row__error">{source.lastError}</p> : null}
      </div>
      <div className="source-health-row__status">
        <Tag type={source.isActive ? "green" : "warm-gray"} size="sm">
          {source.isActive ? "active" : "paused"}
        </Tag>
        {hasErrors ? <Tag type="red" size="sm">{source.fetchErrorCount} errors</Tag> : null}
        <Button
          kind="ghost"
          size="sm"
          disabled={disabled}
          onClick={() => onToggle(source.id, !source.isActive)}
        >
          {source.isActive ? "Pause" : "Resume"}
        </Button>
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
    <form className="topic-form" onSubmit={handleSubmit}>
      <TextInput
        id="signal-topic-name"
        labelText="Topic"
        value={name}
        onChange={(event) => setName(event.currentTarget.value)}
        placeholder="Local-first AI tooling"
      />
      <TextArea
        id="signal-topic-description"
        labelText="Preference"
        value={description}
        onChange={(event) => setDescription(event.currentTarget.value)}
        placeholder="Prefer practical implementation notes over launch commentary."
      />
      <Button type="submit" disabled={mutation.isPending || !name.trim()}>
        {mutation.isPending ? "Saving..." : "Save topic"}
      </Button>
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
    <section className="page-section signal-page">
      <div className="page-heading-group">
        <h1>Signals</h1>
        <p className="page-subtitle">Ranked source items for the weekly triage loop.</p>
      </div>

      {healthQuery.isLoading ? <InlineLoading description="Checking signal health..." /> : null}
      {!chromaReady ? (
        <InlineNotification
          kind="warning"
          title="Signal scoring is paused"
          subtitle="Chroma is required for personalization and similarity scoring."
          hideCloseButton
        />
      ) : null}
      {signalsQuery.error ? (
        <InlineNotification
          kind="error"
          title="Signals could not load"
          subtitle={(signalsQuery.error as Error).message}
          hideCloseButton
        />
      ) : null}

      <div className="signal-health-strip">
        <Tile>
          <span className="rtk-label">Chroma</span>
          <strong>{healthQuery.data?.chroma.ready ? "Ready" : "Unavailable"}</strong>
        </Tile>
        <Tile>
          <span className="rtk-label">Sources</span>
          <strong>{healthQuery.data?.sources.total ?? sourceRows.length}</strong>
        </Tile>
        <Tile>
          <span className="rtk-label">Errored</span>
          <strong>{healthQuery.data?.sources.errored ?? sourceRows.filter((row) => row.fetchErrorCount > 0).length}</strong>
        </Tile>
      </div>

      <div className="signal-layout">
        <div className="signal-queue">
          <div className="section-heading-row">
            <h2>Queue</h2>
            <Tag type="blue" size="sm">{queuedSignals.length}</Tag>
          </div>
          {signalsQuery.isLoading ? <InlineLoading description="Loading signals..." /> : null}
          {!signalsQuery.isLoading && queuedSignals.length === 0 ? (
            <Tile className="empty-panel">
              <h3>No queued signals</h3>
              <p className="page-subtitle">New items appear here after RSS or Telegram channel ingestion runs.</p>
            </Tile>
          ) : null}
          <div className="signal-card-list">
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

        <aside className="signal-sidebar">
          <Tile className="signal-panel">
            <h2>Topics</h2>
            <TopicForm />
          </Tile>

          <Tile className="signal-panel">
            <div className="section-heading-row">
              <h2>Sources</h2>
              <Tag type="gray" size="sm">{sourceRows.length}</Tag>
            </div>
            {sourcesQuery.isLoading ? <InlineLoading description="Loading sources..." /> : null}
            {sourceRows.length === 0 && !sourcesQuery.isLoading ? (
              <p className="page-subtitle">No signal sources are subscribed yet.</p>
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
          </Tile>
        </aside>
      </div>

      {actedSignals.length > 0 ? (
        <section className="signal-history">
          <div className="section-heading-row">
            <h2>Recent decisions</h2>
            <Tag type="gray" size="sm">{actedSignals.length}</Tag>
          </div>
          <div className="signal-history-list">
            {actedSignals.slice(0, 8).map((signal) => (
              <div key={signal.id} className="signal-history-row">
                <span>{signal.feedItemTitle || "Untitled signal"}</span>
                <Tag type={statusTone(signal.status)} size="sm">{signal.status}</Tag>
              </div>
            ))}
          </div>
        </section>
      ) : null}
    </section>
  );
}
