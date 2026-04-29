import { useMemo, useState } from "react";
import {
  Button,
  Checkbox,
  DataTable,
  DataTableSkeleton,
  InlineLoading,
  InlineNotification,
  Modal,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableHeader,
  TableRow,
  TextInput,
  Tag,
  Tile,
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

function statusTagType(status: string): "green" | "warm-gray" | "red" {
  if (status === "active") return "green";
  if (status === "paused") return "warm-gray";
  return "red";
}

function maskSecret(last8: string): string {
  return `${"*".repeat(24)}${last8}`;
}

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
    <fieldset className="cds--fieldset">
      <legend className="cds--label">Event types</legend>
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

  if (isLoading) return <InlineLoading description="Loading deliveries..." />;
  if (error) return <QueryErrorNotification error={error} title="Failed to load deliveries" />;
  if (deliveries.length === 0) {
    return <p className="cds--label">No deliveries yet.</p>;
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
    <DataTable rows={rows} headers={headers}>
      {({ rows, headers, getHeaderProps, getRowProps, getTableProps }) => (
        <TableContainer title="Delivery history">
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
        </TableContainer>
      )}
    </DataTable>
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
    <section className="page-section">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
        <h1>Webhooks</h1>
        <Button kind="primary" onClick={openCreate}>
          Create webhook
        </Button>
      </div>

      {firstMutationError && (
        <InlineNotification
          kind="error"
          title="Action failed"
          subtitle={firstMutationError.message}
          hideCloseButton
        />
      )}

      {testResult && (
        <InlineNotification
          kind={testResult.success ? "success" : "error"}
          title={`Test webhook #${testResult.id}`}
          subtitle={testResult.detail}
          onCloseButtonClick={() => setTestResult(null)}
          style={{ marginBottom: "1rem" }}
        />
      )}

      {revealedSecret && (
        <InlineNotification
          kind="info"
          title={`Secret for webhook #${revealedSecret.id}`}
          subtitle="This secret is shown only once. Copy it now."
          onCloseButtonClick={() => setRevealedSecret(null)}
          style={{ marginBottom: "1rem" }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginTop: "0.5rem" }}>
            <code style={{ fontSize: "0.875rem", wordBreak: "break-all" }}>{revealedSecret.secret}</code>
            <Button kind="ghost" size="sm" onClick={() => void handleCopySecret(revealedSecret.secret)}>
              Copy
            </Button>
          </div>
        </InlineNotification>
      )}

      {webhooksQuery.isLoading && <DataTableSkeleton columnCount={headers.length} rowCount={4} showToolbar={false} />}
      <QueryErrorNotification error={webhooksQuery.error} title="Failed to load webhooks" />

      {!webhooksQuery.isLoading && webhooks.length === 0 && !webhooksQuery.error && (
        <Tile>
          <div className="page-heading-group">
            <h3>No webhooks configured</h3>
            <p className="page-subtitle">
              Webhooks let external services receive notifications when events occur, such as a new summary being created.
            </p>
          </div>
          <div className="form-actions">
            <Button kind="primary" size="sm" onClick={openCreate}>
              Create your first webhook
            </Button>
          </div>
        </Tile>
      )}

      {webhooks.length > 0 && (
        <DataTable rows={rows} headers={headers}>
          {({ rows, headers, getHeaderProps, getRowProps, getTableProps }) => (
            <TableContainer title="Webhook subscriptions">
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
                    const wh = row.cells.find((c) => c.info.header === "Actions")?.value as Webhook;
                    return (
                      <TableRow {...getRowProps({ row })}>
                        {row.cells.map((cell) => {
                          if (cell.info.header === "Status") {
                            const status = cell.value as string;
                            return (
                              <TableCell key={cell.id}>
                                <Tag type={statusTagType(status)} size="sm">
                                  {status}
                                </Tag>
                              </TableCell>
                            );
                          }
                          if (cell.info.header === "Secret") {
                            const last8 = cell.value as string;
                            return (
                              <TableCell key={cell.id}>
                                <code style={{ fontSize: "0.8125rem" }}>{maskSecret(last8)}</code>
                                <div style={{ display: "flex", gap: "0.25rem", marginTop: "0.25rem" }}>
                                  <Button
                                    kind="ghost"
                                    size="sm"
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      void handleCopySecret(maskSecret(last8));
                                    }}
                                  >
                                    Copy
                                  </Button>
                                  <Button
                                    kind="ghost"
                                    size="sm"
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      handleRotate(wh.id);
                                    }}
                                    disabled={rotateMutation.isPending}
                                  >
                                    Rotate
                                  </Button>
                                </div>
                              </TableCell>
                            );
                          }
                          if (cell.info.header === "Actions") {
                            return (
                              <TableCell key={cell.id}>
                                <div className="table-actions">
                                  <Button
                                    kind="ghost"
                                    size="sm"
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      openEdit(wh);
                                    }}
                                  >
                                    Edit
                                  </Button>
                                  <Button
                                    kind="ghost"
                                    size="sm"
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      handleTest(wh.id);
                                    }}
                                    disabled={testMutation.isPending}
                                  >
                                    Test
                                  </Button>
                                  <Button
                                    kind="ghost"
                                    size="sm"
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      setDeliveryWebhookId(deliveryWebhookId === wh.id ? null : wh.id);
                                    }}
                                  >
                                    {deliveryWebhookId === wh.id ? "Hide log" : "Deliveries"}
                                  </Button>
                                  <Button
                                    kind="danger--ghost"
                                    size="sm"
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      setDeleteTarget(wh);
                                    }}
                                    disabled={deleteMutation.isPending}
                                  >
                                    Delete
                                  </Button>
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
            </TableContainer>
          )}
        </DataTable>
      )}

      {deliveryWebhookId != null && (
        <div style={{ marginTop: "1rem" }}>
          <DeliveryLog webhookId={deliveryWebhookId} />
        </div>
      )}

      {/* Create modal */}
      <Modal
        open={createOpen}
        modalHeading="Create webhook"
        primaryButtonText={createMutation.isPending ? "Creating..." : "Create"}
        secondaryButtonText="Cancel"
        primaryButtonDisabled={!canCreate || createMutation.isPending}
        onRequestClose={() => {
          if (!createMutation.isPending) setCreateOpen(false);
        }}
        onRequestSubmit={handleCreate}
      >
        <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
          <TextInput
            id="webhook-create-name"
            labelText="Name (optional)"
            value={createName}
            onChange={(e) => setCreateName(e.currentTarget.value)}
            placeholder="My webhook"
          />
          <TextInput
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
      </Modal>

      {/* Edit modal */}
      <Modal
        open={editWebhook != null}
        modalHeading="Edit webhook"
        primaryButtonText={updateMutation.isPending ? "Saving..." : "Save"}
        secondaryButtonText="Cancel"
        primaryButtonDisabled={!canUpdate || updateMutation.isPending}
        onRequestClose={() => {
          if (!updateMutation.isPending) setEditWebhook(null);
        }}
        onRequestSubmit={handleUpdate}
      >
        <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
          <TextInput
            id="webhook-edit-name"
            labelText="Name (optional)"
            value={editName}
            onChange={(e) => setEditName(e.currentTarget.value)}
          />
          <TextInput
            id="webhook-edit-url"
            labelText="URL"
            value={editUrl}
            onChange={(e) => setEditUrl(e.currentTarget.value)}
            invalid={editUrl.length > 0 && !editUrl.startsWith("http")}
            invalidText="URL must start with http:// or https://"
          />
          <EventCheckboxGroup selected={editEvents} onChange={setEditEvents} />
        </div>
      </Modal>

      {/* Delete confirmation */}
      <Modal
        open={deleteTarget != null}
        modalHeading="Delete webhook"
        primaryButtonText={deleteMutation.isPending ? "Deleting..." : "Delete"}
        secondaryButtonText="Cancel"
        danger
        onRequestClose={() => {
          if (!deleteMutation.isPending) setDeleteTarget(null);
        }}
        onRequestSubmit={handleDelete}
      >
        <p>
          {deleteTarget
            ? `Delete "${deleteTarget.name ?? `Webhook #${deleteTarget.id}`}"? This action cannot be undone.`
            : "Delete selected webhook?"}
        </p>
      </Modal>
    </section>
  );
}
