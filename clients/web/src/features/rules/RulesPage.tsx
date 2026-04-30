import { useMemo, useState } from "react";
import {
  BracketButton,
  BrutalistCard,
  BrutalistDataTableSkeleton,
  BrutalistModal,
  BrutalistTable,
  BrutalistTableContainer,
  StatusBadge,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  Toggle,
} from "../../design";
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
          Rules
        </h1>
        <BracketButton kind="primary" onClick={openCreate}>
          Create Rule
        </BracketButton>
      </div>

      {firstMutationError && (
        <StatusBadge severity="alarm" title="Action failed" subtitle={firstMutationError.message} />
      )}

      {testResult && (
        <StatusBadge
          severity={testResult.matched ? "info" : "warn"}
          title={`${testResult.matched ? "✓ " : ""}Test rule #${testResult.ruleId}`}
          subtitle={testResult.detail}
          dismissible
          onDismiss={() => setTestResult(null)}
        />
      )}

      {rulesQuery.isLoading && (
        <BrutalistDataTableSkeleton columnCount={headers.length} rowCount={4} showToolbar={false} />
      )}
      <QueryErrorNotification error={rulesQuery.error} title="Failed to load rules" />

      {!rulesQuery.isLoading && rules.length === 0 && !rulesQuery.error && (
        <BrutalistCard>
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
            No automation rules
          </h3>
          <p
            style={{
              fontFamily: "var(--frost-font-mono)",
              fontSize: "var(--frost-type-mono-body-size)",
              color: "color-mix(in oklch, var(--frost-ink) 55%, transparent)",
              margin: "var(--frost-gap-row) 0 0",
            }}
          >
            Rules run automatically when events occur and can trigger actions such as tagging or forwarding summaries.
          </p>
          <div style={{ marginTop: "var(--frost-gap-section)" }}>
            <BracketButton kind="primary" size="sm" onClick={openCreate}>
              Create your first rule
            </BracketButton>
          </div>
        </BrutalistCard>
      )}

      {rules.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--frost-gap-row)" }}>
          <p style={sectionLabelStyle}>§ ACTIVE RULES</p>
          <BrutalistTable rows={rows} headers={headers}>
            {({ rows, headers, getHeaderProps, getRowProps, getTableProps }) => (
              <BrutalistTableContainer title="Automation rules">
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
                                  <div style={{ display: "flex", gap: "var(--frost-gap-row)", flexWrap: "wrap" }}>
                                    <BracketButton
                                      kind="ghost"
                                      size="sm"
                                      onClick={(e) => {
                                        e.stopPropagation();
                                        openEdit(ruleObj);
                                      }}
                                    >
                                      Edit
                                    </BracketButton>
                                    <BracketButton
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
                                    </BracketButton>
                                    <BracketButton
                                      kind="danger--ghost"
                                      size="sm"
                                      onClick={(e) => {
                                        e.stopPropagation();
                                        setDeleteTarget(ruleObj);
                                      }}
                                      disabled={deleteMutation.isPending}
                                    >
                                      Delete
                                    </BracketButton>
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
              </BrutalistTableContainer>
            )}
          </BrutalistTable>
        </div>
      )}

      {logRuleId != null && (
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--frost-gap-row)" }}>
          <p style={sectionLabelStyle}>§ RULE LOG</p>
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
      <BrutalistModal
        open={deleteTarget != null}
        danger
        modalHeading="Delete Rule"
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
            ? `Delete "${deleteTarget.name}"? This action cannot be undone.`
            : "Delete selected rule?"}
        </p>
      </BrutalistModal>
    </main>
  );
}
