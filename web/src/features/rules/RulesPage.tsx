import { useMemo, useState } from "react";
import {
  Button,
  DataTable,
  DataTableSkeleton,
  InlineNotification,
  Modal,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableHeader,
  TableRow,
  Toggle,
} from "@carbon/react";
import { QueryErrorNotification } from "../../components/QueryErrorNotification";
import {
  useRules,
  useCreateRule,
  useUpdateRule,
  useDeleteRule,
  useTestRule,
} from "../../hooks/useRules";
import type { Rule, CreateRulePayload, UpdateRulePayload } from "../../api/rules";
import RuleEditor from "./RuleEditor";
import RuleLogViewer from "./RuleLogViewer";

export default function RulesPage() {
  // --- list query ---
  const rulesQuery = useRules();
  const rules: Rule[] = useMemo(() => rulesQuery.data ?? [], [rulesQuery.data]);

  // --- mutations ---
  const createMutation = useCreateRule();
  const updateMutation = useUpdateRule();
  const deleteMutation = useDeleteRule();
  const testMutation = useTestRule();

  // --- create/edit modal ---
  const [editorOpen, setEditorOpen] = useState(false);
  const [editRule, setEditRule] = useState<Rule | null>(null);

  // --- delete confirmation ---
  const [deleteTarget, setDeleteTarget] = useState<Rule | null>(null);

  // --- log viewer ---
  const [logRuleId, setLogRuleId] = useState<number | null>(null);

  // --- test result ---
  const [testResult, setTestResult] = useState<{
    ruleId: number;
    matched: boolean;
    detail: string;
  } | null>(null);

  // --- table ---
  const headers = [
    { key: "name", header: "Name" },
    { key: "eventType", header: "Event Type" },
    { key: "enabled", header: "Enabled" },
    { key: "runCount", header: "Run Count" },
    { key: "lastTriggeredAt", header: "Last Triggered" },
    { key: "actions", header: "Actions" },
  ];

  const rows = useMemo(
    () =>
      rules.map((r) => ({
        id: String(r.id),
        name: r.name,
        eventType: r.eventType,
        enabled: r,
        runCount: String(r.runCount),
        lastTriggeredAt: r.lastTriggeredAt
          ? new Date(r.lastTriggeredAt).toLocaleString()
          : "Never",
        actions: r,
      })),
    [rules],
  );

  // --- handlers ---

  function openCreate(): void {
    setEditRule(null);
    setEditorOpen(true);
  }

  function openEdit(rule: Rule): void {
    setEditRule(rule);
    setEditorOpen(true);
  }

  function handleSave(payload: CreateRulePayload | UpdateRulePayload): void {
    if (editRule) {
      updateMutation.mutate(
        { id: editRule.id, data: payload as UpdateRulePayload },
        { onSuccess: () => setEditorOpen(false) },
      );
    } else {
      createMutation.mutate(payload as CreateRulePayload, {
        onSuccess: () => setEditorOpen(false),
      });
    }
  }

  function handleDelete(): void {
    if (!deleteTarget) return;
    deleteMutation.mutate(deleteTarget.id, {
      onSuccess: () => setDeleteTarget(null),
    });
  }

  function handleToggleEnabled(rule: Rule): void {
    updateMutation.mutate({
      id: rule.id,
      data: { enabled: !rule.enabled },
    });
  }

  function handleTest(ruleId: number, summaryId: number): void {
    testMutation.mutate(
      { id: ruleId, summaryId },
      {
        onSuccess: (result) => {
          const detail = result.matched
            ? `Matched. Actions: ${JSON.stringify(result.actionsTaken)}`
            : "No match.";
          setTestResult({ ruleId, matched: result.matched, detail });
        },
        onError: (err) => {
          setTestResult({
            ruleId,
            matched: false,
            detail: (err as Error).message,
          });
        },
      },
    );
  }

  const isSaving = createMutation.isPending || updateMutation.isPending;

  const firstMutationError = [
    createMutation.error,
    updateMutation.error,
    deleteMutation.error,
    testMutation.error,
  ].find((e): e is Error => e instanceof Error);

  return (
    <section className="page-section">
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: "1rem",
        }}
      >
        <h1>Rules</h1>
        <Button kind="primary" onClick={openCreate}>
          Create rule
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
          kind={testResult.matched ? "success" : "warning"}
          title={`Test rule #${testResult.ruleId}`}
          subtitle={testResult.detail}
          onCloseButtonClick={() => setTestResult(null)}
          style={{ marginBottom: "1rem" }}
        />
      )}

      {rulesQuery.isLoading && (
        <DataTableSkeleton columnCount={headers.length} rowCount={4} showToolbar={false} />
      )}
      <QueryErrorNotification error={rulesQuery.error} title="Failed to load rules" />

      {!rulesQuery.isLoading && rules.length === 0 && !rulesQuery.error && (
        <p>No rules yet. Create one to get started.</p>
      )}

      {rules.length > 0 && (
        <DataTable rows={rows} headers={headers}>
          {({ rows, headers, getHeaderProps, getRowProps, getTableProps }) => (
            <TableContainer title="Automation rules">
              <Table {...getTableProps()}>
                <TableHead>
                  <TableRow>
                    {headers.map((header) => (
                      <TableHeader {...getHeaderProps({ header })}>
                        {header.header}
                      </TableHeader>
                    ))}
                  </TableRow>
                </TableHead>
                <TableBody>
                  {rows.map((row) => {
                    const ruleObj = row.cells.find(
                      (c) => c.info.header === "actions",
                    )?.value as Rule;
                    return (
                      <TableRow {...getRowProps({ row })}>
                        {row.cells.map((cell) => {
                          if (cell.info.header === "enabled") {
                            const r = cell.value as Rule;
                            return (
                              <TableCell key={cell.id}>
                                <Toggle
                                  id={`toggle-${r.id}`}
                                  size="sm"
                                  labelA=""
                                  labelB=""
                                  toggled={r.enabled}
                                  onToggle={() => handleToggleEnabled(r)}
                                  disabled={updateMutation.isPending}
                                />
                              </TableCell>
                            );
                          }
                          if (cell.info.header === "actions") {
                            return (
                              <TableCell key={cell.id}>
                                <div className="table-actions">
                                  <Button
                                    kind="ghost"
                                    size="sm"
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      openEdit(ruleObj);
                                    }}
                                  >
                                    Edit
                                  </Button>
                                  <Button
                                    kind="ghost"
                                    size="sm"
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      setLogRuleId(
                                        logRuleId === ruleObj.id ? null : ruleObj.id,
                                      );
                                    }}
                                  >
                                    {logRuleId === ruleObj.id ? "Hide logs" : "Logs"}
                                  </Button>
                                  <Button
                                    kind="danger--ghost"
                                    size="sm"
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      setDeleteTarget(ruleObj);
                                    }}
                                    disabled={deleteMutation.isPending}
                                  >
                                    Delete
                                  </Button>
                                </div>
                              </TableCell>
                            );
                          }
                          return (
                            <TableCell key={cell.id}>
                              {cell.value as string}
                            </TableCell>
                          );
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

      {logRuleId != null && (
        <div style={{ marginTop: "1rem" }}>
          <RuleLogViewer ruleId={logRuleId} />
        </div>
      )}

      {/* Editor modal -- key forces remount on rule change */}
      {editorOpen && (
        <RuleEditor
          key={editRule?.id ?? "create"}
          open={editorOpen}
          rule={editRule}
          onClose={() => setEditorOpen(false)}
          onSave={handleSave}
          onTest={handleTest}
          isSaving={isSaving}
        />
      )}

      {/* Delete confirmation */}
      <Modal
        open={deleteTarget != null}
        modalHeading="Delete rule"
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
            ? `Delete "${deleteTarget.name}"? This action cannot be undone.`
            : "Delete selected rule?"}
        </p>
      </Modal>
    </section>
  );
}
