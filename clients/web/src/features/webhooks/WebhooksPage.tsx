import { useMemo, useState } from "react";
import {
  BracketButton,
  BrutalistCard,
  BrutalistDataTableSkeleton,
  BrutalistModal,
  BrutalistModalBody,
  BrutalistModalFooter,
  BrutalistModalHeader,
  BrutalistTable,
  BrutalistTableContainer,
  Checkbox,
  MonoInput,
  SparkLoading,
  StatusBadge,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  Tag,
} from "../../design";
import { QueryErrorNotification } from "../../components/QueryErrorNotification";
import {
  useWebhooks,
  useCreateWebhook,
  useUpdateWebhook,
  useDeleteWebhook,
  useTestWebhook,
  useDeliveries,
  useRotateSecret,
} from "../../hooks/useWebhooks";
import type {
  Webhook,
  WebhookDetail,
  WebhookEventType,
  WebhookDelivery,
} from "../../api/webhooks";
import { WEBHOOK_EVENT_TYPES } from "../../api/webhooks";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function maskSecret(last8: string): string {
  return `${"*".repeat(24)}${last8}`;
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

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function EventCheckboxGroup({
  selected,
  onChange,
}: {
  selected: WebhookEventType[];
  onChange: (events: WebhookEventType[]) => void;
}) {
  return (
    <fieldset className="rtk-fieldset">
      <legend className="rtk-label">Event types</legend>
      {WEBHOOK_EVENT_TYPES.map((evt) => (
        <Checkbox
          key={evt}
          id={`event-${evt}`}
          labelText={evt}
          checked={selected.includes(evt)}
          onChange={(_event: React.ChangeEvent<HTMLInputElement>, { checked }: { checked: boolean }) => {
            if (checked) {
              onChange([...selected, evt]);
            } else {
              onChange(selected.filter((e) => e !== evt));
            }
          }}
        />
      ))}
    </fieldset>
  );
}

function DeliveryLog({ webhookId }: { webhookId: number }) {
  const { data, isLoading, error } = useDeliveries(webhookId);
  const deliveries: WebhookDelivery[] = data?.deliveries ?? [];

  if (isLoading) return <SparkLoading description="Loading deliveries..." />;
  if (error) return <QueryErrorNotification error={error} title="Failed to load deliveries" />;
  if (deliveries.length === 0) {
    return <p style={monoBodyStyle}>No deliveries yet.</p>;
  }

  const headers = [
    { key: "deliveredAt", header: "Time" },
    { key: "eventType", header: "Event" },
    { key: "statusCode", header: "Status" },
    { key: "success", header: "Result" },
    { key: "durationMs", header: "Duration" },
    { key: "errorMessage", header: "Error" },
  ];

  const rows = deliveries.map((d) => ({
    id: String(d.id),
    deliveredAt: new Date(d.deliveredAt).toLocaleString(),
    eventType: d.eventType,
    statusCode: d.statusCode != null ? String(d.statusCode) : "-",
    success: d.success ? "OK" : "FAIL",
    durationMs: d.durationMs != null ? `${d.durationMs}ms` : "-",
    errorMessage: d.errorMessage ?? "",
  }));

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--frost-gap-row)" }}>
      <p style={sectionLabelStyle}>§ DELIVERY HISTORY</p>
      <BrutalistTable rows={rows} headers={headers}>
        {({ rows, headers, getHeaderProps, getRowProps, getTableProps }) => (
          <BrutalistTableContainer title="Delivery history">
            <Table {...getTableProps()} size="sm">
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
                      <TableCell key={cell.id}>{cell.value as string}</TableCell>
                    ))}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </BrutalistTableContainer>
        )}
      </BrutalistTable>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function WebhooksPage() {
  // --- list query ---
  const webhooksQuery = useWebhooks();
  const webhooks: Webhook[] = useMemo(() => webhooksQuery.data ?? [], [webhooksQuery.data]);

  // --- mutations ---
  const createMutation = useCreateWebhook();
  const updateMutation = useUpdateWebhook();
  const deleteMutation = useDeleteWebhook();
  const testMutation = useTestWebhook();
  const rotateMutation = useRotateSecret();

  // --- create modal ---
  const [createOpen, setCreateOpen] = useState(false);
  const [createName, setCreateName] = useState("");
  const [createUrl, setCreateUrl] = useState("");
  const [createEvents, setCreateEvents] = useState<WebhookEventType[]>([]);

  // --- edit modal ---
  const [editWebhook, setEditWebhook] = useState<Webhook | null>(null);
  const [editName, setEditName] = useState("");
  const [editUrl, setEditUrl] = useState("");
  const [editEvents, setEditEvents] = useState<WebhookEventType[]>([]);

  // --- delete confirmation ---
  const [deleteTarget, setDeleteTarget] = useState<Webhook | null>(null);

  // --- delivery log ---
  const [deliveryWebhookId, setDeliveryWebhookId] = useState<number | null>(null);

  // --- secret display ---
  const [revealedSecret, setRevealedSecret] = useState<{ id: number; secret: string } | null>(null);

  // --- test result ---
  const [testResult, setTestResult] = useState<{ id: number; success: boolean; detail: string } | null>(null);

  // --- table ---
  const headers = [
    { key: "name", header: "Name" },
    { key: "url", header: "URL" },
    { key: "events", header: "Events" },
    { key: "status", header: "Status" },
    { key: "failureCount", header: "Failures" },
    { key: "secret", header: "Secret" },
    { key: "actions", header: "Actions" },
  ];

  const rows = useMemo(
    () =>
      webhooks.map((wh) => ({
        id: String(wh.id),
        name: wh.name ?? `Webhook #${wh.id}`,
        url: wh.url,
        events: wh.events.join(", "),
        status: wh.status,
        failureCount: String(wh.failureCount),
        secret: wh.secretLast8,
        actions: wh,
      })),
    [webhooks],
  );

  // --- handlers ---

  function openCreate(): void {
    setCreateName("");
    setCreateUrl("");
    setCreateEvents([]);
    setCreateOpen(true);
  }

  function handleCreate(): void {
    createMutation.mutate(
      {
        name: createName.trim() || undefined,
        url: createUrl.trim(),
        events: createEvents,
      },
      {
        onSuccess: (created: WebhookDetail) => {
          setCreateOpen(false);
          if (created.secret) {
            setRevealedSecret({ id: created.id, secret: created.secret });
          }
        },
      },
    );
  }

  function openEdit(wh: Webhook): void {
    setEditWebhook(wh);
    setEditName(wh.name ?? "");
    setEditUrl(wh.url);
    setEditEvents([...wh.events]);
  }

  function handleUpdate(): void {
    if (!editWebhook) return;
    updateMutation.mutate(
      {
        id: editWebhook.id,
        data: {
          name: editName.trim() || null,
          url: editUrl.trim(),
          events: editEvents,
        },
      },
      {
        onSuccess: () => setEditWebhook(null),
      },
    );
  }

  function handleDelete(): void {
    if (!deleteTarget) return;
    deleteMutation.mutate(deleteTarget.id, {
      onSuccess: () => setDeleteTarget(null),
    });
  }

  function handleTest(id: number): void {
    testMutation.mutate(id, {
      onSuccess: (result) => {
        const detail = result.success
          ? `Status ${result.statusCode ?? "OK"}`
          : result.error ?? "Failed";
        setTestResult({ id, success: result.success, detail });
      },
      onError: (err) => {
        setTestResult({ id, success: false, detail: (err as Error).message });
      },
    });
  }

  function handleRotate(id: number): void {
    rotateMutation.mutate(id, {
      onSuccess: (result) => {
        setRevealedSecret({ id, secret: result.secret });
      },
    });
  }

  async function handleCopySecret(text: string): Promise<void> {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      // Clipboard API may be unavailable in some environments
    }
  }

  const canCreate = createUrl.trim().length > 0 && createEvents.length > 0;
  const canUpdate = editUrl.trim().length > 0 && editEvents.length > 0;

  const firstMutationError = [
    createMutation.error,
    updateMutation.error,
    deleteMutation.error,
    testMutation.error,
    rotateMutation.error,
  ].find((e): e is Error => e instanceof Error);

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
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h1
          style={{
            fontFamily: "var(--frost-font-mono)",
            fontSize: "var(--frost-type-mono-emph-size)",
            fontWeight: "var(--frost-type-mono-emph-weight)" as React.CSSProperties["fontWeight"],
            letterSpacing: "var(--frost-type-mono-emph-tracking)",
            textTransform: "uppercase",
            color: "var(--frost-ink)",
            margin: 0,
          }}
        >
          Webhooks
        </h1>
        <BracketButton kind="primary" onClick={openCreate}>
          Create Webhook
        </BracketButton>
      </div>

      {firstMutationError && (
        <StatusBadge severity="alarm" title="Action failed" subtitle={firstMutationError.message} />
      )}

      {testResult && (
        <StatusBadge
          severity={testResult.success ? "info" : "alarm"}
          title={`${testResult.success ? "✓ " : ""}Test webhook #${testResult.id}`}
          subtitle={testResult.detail}
          dismissible
          onDismiss={() => setTestResult(null)}
        />
      )}

      {revealedSecret && (
        <StatusBadge
          severity="info"
          title={`✓ Secret for webhook #${revealedSecret.id}`}
          subtitle="This secret is shown only once. Copy it now."
          dismissible
          onDismiss={() => setRevealedSecret(null)}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "var(--frost-gap-row)", marginTop: "var(--frost-gap-row)" }}>
            <code style={{ fontFamily: "var(--frost-font-mono)", fontSize: "var(--frost-type-mono-body-size)", wordBreak: "break-all" }}>
              {revealedSecret.secret}
            </code>
            <BracketButton kind="ghost" size="sm" onClick={() => void handleCopySecret(revealedSecret.secret)}>
              Copy
            </BracketButton>
          </div>
        </StatusBadge>
      )}

      {webhooksQuery.isLoading && (
        <BrutalistDataTableSkeleton columnCount={headers.length} rowCount={4} showToolbar={false} />
      )}
      <QueryErrorNotification error={webhooksQuery.error} title="Failed to load webhooks" />

      {!webhooksQuery.isLoading && webhooks.length === 0 && !webhooksQuery.error && (
        <BrutalistCard>
          <div className="page-heading-group">
            <h3
              style={{
                fontFamily: "var(--frost-font-mono)",
                fontSize: "var(--frost-type-mono-emph-size)",
                fontWeight: "var(--frost-type-mono-emph-weight)" as React.CSSProperties["fontWeight"],
                textTransform: "uppercase",
                letterSpacing: "var(--frost-type-mono-emph-tracking)",
                color: "var(--frost-ink)",
                margin: 0,
              }}
            >
              No webhooks configured
            </h3>
            <p
              style={{
                fontFamily: "var(--frost-font-mono)",
                fontSize: "var(--frost-type-mono-body-size)",
                color: "color-mix(in oklch, var(--frost-ink) 55%, transparent)",
                margin: "var(--frost-gap-row) 0 0",
              }}
            >
              Webhooks let external services receive notifications when events occur, such as a new summary being created.
            </p>
          </div>
          <div style={{ marginTop: "var(--frost-gap-section)" }}>
            <BracketButton kind="primary" size="sm" onClick={openCreate}>
              Create your first webhook
            </BracketButton>
          </div>
        </BrutalistCard>
      )}

      {webhooks.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--frost-gap-row)" }}>
          <p style={sectionLabelStyle}>§ WEBHOOK SUBSCRIPTIONS</p>
          <BrutalistTable rows={rows} headers={headers}>
            {({ rows, headers, getHeaderProps, getRowProps, getTableProps }) => (
              <BrutalistTableContainer title="Webhook subscriptions">
                <Table {...getTableProps()}>
                  <TableHead>
                    <TableRow>
                      {headers.map((header) => (
                        <TableHeader {...getHeaderProps({ header })}>{header.header}</TableHeader>
                      ))}
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {rows.map((row) => {
                      const wh = row.cells.find((c) => c.info.header === "actions")?.value as Webhook;
                      return (
                        <TableRow {...getRowProps({ row })}>
                          {row.cells.map((cell) => {
                            if (cell.info.header === "status") {
                              const status = cell.value as string;
                              return (
                                <TableCell key={cell.id}>
                                  <Tag
                                    type={status === "active" ? "green" : status === "paused" ? "warm-gray" : "red"}
                                    size="sm"
                                  >
                                    {status}
                                  </Tag>
                                </TableCell>
                              );
                            }
                            if (cell.info.header === "secret") {
                              const last8 = cell.value as string;
                              return (
                                <TableCell key={cell.id}>
                                  <code style={{ fontFamily: "var(--frost-font-mono)", fontSize: "var(--frost-type-mono-body-size)" }}>
                                    {maskSecret(last8)}
                                  </code>
                                  <div style={{ display: "flex", gap: "var(--frost-gap-row)", marginTop: "4px" }}>
                                    <BracketButton
                                      kind="ghost"
                                      size="sm"
                                      onClick={(e) => {
                                        e.stopPropagation();
                                        void handleCopySecret(maskSecret(last8));
                                      }}
                                    >
                                      Copy
                                    </BracketButton>
                                    <BracketButton
                                      kind="ghost"
                                      size="sm"
                                      onClick={(e) => {
                                        e.stopPropagation();
                                        handleRotate(wh.id);
                                      }}
                                      disabled={rotateMutation.isPending}
                                    >
                                      Rotate
                                    </BracketButton>
                                  </div>
                                </TableCell>
                              );
                            }
                            if (cell.info.header === "actions") {
                              return (
                                <TableCell key={cell.id}>
                                  <div style={{ display: "flex", gap: "var(--frost-gap-row)", flexWrap: "wrap" }}>
                                    <BracketButton
                                      kind="ghost"
                                      size="sm"
                                      onClick={(e) => {
                                        e.stopPropagation();
                                        openEdit(wh);
                                      }}
                                    >
                                      Edit
                                    </BracketButton>
                                    <BracketButton
                                      kind="ghost"
                                      size="sm"
                                      onClick={(e) => {
                                        e.stopPropagation();
                                        handleTest(wh.id);
                                      }}
                                      disabled={testMutation.isPending}
                                    >
                                      {testMutation.isPending ? "Testing..." : "Test"}
                                    </BracketButton>
                                    <BracketButton
                                      kind="ghost"
                                      size="sm"
                                      onClick={(e) => {
                                        e.stopPropagation();
                                        setDeliveryWebhookId(deliveryWebhookId === wh.id ? null : wh.id);
                                      }}
                                    >
                                      {deliveryWebhookId === wh.id ? "Hide log" : "Deliveries"}
                                    </BracketButton>
                                    <BracketButton
                                      kind="danger--ghost"
                                      size="sm"
                                      onClick={(e) => {
                                        e.stopPropagation();
                                        setDeleteTarget(wh);
                                      }}
                                      disabled={deleteMutation.isPending}
                                    >
                                      Delete
                                    </BracketButton>
                                  </div>
                                </TableCell>
                              );
                            }
                            return <TableCell key={cell.id}>{cell.value as string}</TableCell>;
                          })}
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>
              </BrutalistTableContainer>
            )}
          </BrutalistTable>
        </div>
      )}

      {testMutation.isPending && (
        <SparkLoading description="Sending test webhook..." />
      )}

      {deliveryWebhookId != null && (
        <DeliveryLog webhookId={deliveryWebhookId} />
      )}

      {/* Create modal */}
      <BrutalistModal
        open={createOpen}
        size="md"
        onRequestClose={() => {
          if (!createMutation.isPending) setCreateOpen(false);
        }}
      >
        <BrutalistModalHeader title="Create Webhook" />
        <BrutalistModalBody>
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--frost-gap-section)" }}>
            <MonoInput
              id="webhook-create-name"
              labelText="Name (optional)"
              value={createName}
              onChange={(e) => setCreateName(e.currentTarget.value)}
              placeholder="My webhook"
            />
            <MonoInput
              id="webhook-create-url"
              labelText="URL"
              value={createUrl}
              onChange={(e) => setCreateUrl(e.currentTarget.value)}
              placeholder="https://example.com/webhook"
              invalid={createUrl.length > 0 && !createUrl.startsWith("http")}
              invalidText="URL must start with http:// or https://"
            />
            <EventCheckboxGroup selected={createEvents} onChange={setCreateEvents} />
          </div>
        </BrutalistModalBody>
        <BrutalistModalFooter>
          <BracketButton
            kind="ghost"
            onClick={() => {
              if (!createMutation.isPending) setCreateOpen(false);
            }}
          >
            Cancel
          </BracketButton>
          <BracketButton
            kind="primary"
            disabled={!canCreate || createMutation.isPending}
            onClick={handleCreate}
          >
            {createMutation.isPending ? "Creating..." : "Create"}
          </BracketButton>
        </BrutalistModalFooter>
      </BrutalistModal>

      {/* Edit modal */}
      <BrutalistModal
        open={editWebhook != null}
        size="md"
        onRequestClose={() => {
          if (!updateMutation.isPending) setEditWebhook(null);
        }}
      >
        <BrutalistModalHeader title="Edit Webhook" />
        <BrutalistModalBody>
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--frost-gap-section)" }}>
            <MonoInput
              id="webhook-edit-name"
              labelText="Name (optional)"
              value={editName}
              onChange={(e) => setEditName(e.currentTarget.value)}
            />
            <MonoInput
              id="webhook-edit-url"
              labelText="URL"
              value={editUrl}
              onChange={(e) => setEditUrl(e.currentTarget.value)}
              invalid={editUrl.length > 0 && !editUrl.startsWith("http")}
              invalidText="URL must start with http:// or https://"
            />
            <EventCheckboxGroup selected={editEvents} onChange={setEditEvents} />
          </div>
        </BrutalistModalBody>
        <BrutalistModalFooter>
          <BracketButton
            kind="ghost"
            onClick={() => {
              if (!updateMutation.isPending) setEditWebhook(null);
            }}
          >
            Cancel
          </BracketButton>
          <BracketButton
            kind="primary"
            disabled={!canUpdate || updateMutation.isPending}
            onClick={handleUpdate}
          >
            {updateMutation.isPending ? "Saving..." : "Save"}
          </BracketButton>
        </BrutalistModalFooter>
      </BrutalistModal>

      {/* Delete confirmation */}
      <BrutalistModal
        open={deleteTarget != null}
        danger
        modalHeading="Delete Webhook"
        primaryButtonText={deleteMutation.isPending ? "Deleting..." : "Delete"}
        secondaryButtonText="Cancel"
        primaryButtonDisabled={deleteMutation.isPending}
        onRequestClose={() => {
          if (!deleteMutation.isPending) setDeleteTarget(null);
        }}
        onRequestSubmit={handleDelete}
      >
        <p style={monoBodyStyle}>
          {deleteTarget
            ? `Delete "${deleteTarget.name ?? `Webhook #${deleteTarget.id}`}"? This action cannot be undone.`
            : "Delete selected webhook?"}
        </p>
      </BrutalistModal>
    </main>
  );
}
