import { useMemo, useState } from "react";
import {
  BracketButton,
  BrutalistDataTableSkeleton,
  BrutalistModal,
  BrutalistModalBody,
  BrutalistModalFooter,
  BrutalistModalHeader,
  BrutalistTable,
  BrutalistTableContainer,
  NumberInput,
  MonoSelect,
  MonoSelectItem,
  StatusBadge,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  Tag,
  Toggle,
} from "../../design";
import { QueryErrorNotification } from "../../components/QueryErrorNotification";
import {
  useBackups,
  useCreateBackup,
  useDeleteBackup,
  useBackupSchedule,
  useUpdateSchedule,
} from "../../hooks/useBackups";
import type { Backup, BackupStatus } from "../../api/backups";
import { getBackupDownloadUrl } from "../../api/backups";
import BackupProgress from "./BackupProgress";
import RestoreUpload from "./RestoreUpload";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function statusTagType(status: BackupStatus): "green" | "blue" | "warm-gray" | "red" {
  if (status === "completed") return "green";
  if (status === "processing") return "blue";
  if (status === "failed") return "red";
  return "warm-gray";
}

function formatSize(bytes: number | null): string {
  if (bytes == null) return "-";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString();
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

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function BackupsPage() {
  const backupsQuery = useBackups();
  const backups: Backup[] = useMemo(() => backupsQuery.data ?? [], [backupsQuery.data]);

  const createMutation = useCreateBackup();
  const deleteMutation = useDeleteBackup();

  const scheduleQuery = useBackupSchedule();
  const updateScheduleMutation = useUpdateSchedule();

  const [deleteTarget, setDeleteTarget] = useState<Backup | null>(null);
  const [processingBackupId, setProcessingBackupId] = useState<number | null>(null);

  // --- table ---
  const headers = [
    { key: "type", header: "Type" },
    { key: "status", header: "Status" },
    { key: "size", header: "Size" },
    { key: "items", header: "Items" },
    { key: "date", header: "Created" },
    { key: "actions", header: "Actions" },
  ];

  const rows = useMemo(
    () =>
      backups.map((b) => ({
        id: String(b.id),
        type: b.type,
        status: b.status,
        size: formatSize(b.fileSizeBytes),
        items: b.itemsCount != null ? String(b.itemsCount) : "-",
        date: formatDate(b.createdAt),
        actions: b,
      })),
    [backups],
  );

  function handleCreate(): void {
    createMutation.mutate(undefined, {
      onSuccess: (created) => {
        if (created.status === "pending" || created.status === "processing") {
          setProcessingBackupId(created.id);
        }
      },
    });
  }

  function handleDelete(): void {
    if (!deleteTarget) return;
    deleteMutation.mutate(deleteTarget.id, {
      onSuccess: () => setDeleteTarget(null),
    });
  }

  function handleBackupComplete(): void {
    setProcessingBackupId(null);
    void backupsQuery.refetch();
  }

  // Schedule handlers
  const schedule = scheduleQuery.data;

  function handleToggleEnabled(checked: boolean): void {
    updateScheduleMutation.mutate({ backupEnabled: checked });
  }

  function handleFrequencyChange(value: string): void {
    updateScheduleMutation.mutate({ backupFrequency: value });
  }

  function handleRetentionChange(value: number): void {
    if (value >= 1 && value <= 100) {
      updateScheduleMutation.mutate({ backupRetentionCount: value });
    }
  }

  const firstMutationError = [
    createMutation.error,
    deleteMutation.error,
    updateScheduleMutation.error,
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
          Backups
        </h1>
        <BracketButton
          onClick={handleCreate}
          disabled={createMutation.isPending}
        >
          {createMutation.isPending ? "Creating..." : "Create Backup"}
        </BracketButton>
      </div>

      {firstMutationError && (
        <StatusBadge severity="alarm" title="Action failed" subtitle={firstMutationError.message} />
      )}

      {processingBackupId != null && (
        <BackupProgress backupId={processingBackupId} onComplete={handleBackupComplete} />
      )}

      {backupsQuery.isLoading && (
        <BrutalistDataTableSkeleton columnCount={headers.length} rowCount={4} showToolbar={false} />
      )}
      <QueryErrorNotification error={backupsQuery.error} title="Failed to load backups" />

      {!backupsQuery.isLoading && backups.length === 0 && !backupsQuery.error && (
        <p
          style={{
            fontFamily: "var(--frost-font-mono)",
            fontSize: "var(--frost-type-mono-body-size)",
            color: "color-mix(in oklch, var(--frost-ink) 55%, transparent)",
            margin: 0,
          }}
        >
          No backups yet. Create one to get started.
        </p>
      )}

      {backups.length > 0 && (
        <div>
          <p style={{ ...sectionLabelStyle, marginBottom: "var(--frost-gap-row)" }}>§ BACKUP HISTORY</p>
          <BrutalistTable rows={rows} headers={headers}>
            {({ rows, headers, getHeaderProps, getRowProps, getTableProps }) => (
              <BrutalistTableContainer title="Backup history">
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
                      const backup = row.cells.find((c) => c.info.header === "Actions")?.value as Backup;
                      return (
                        <TableRow {...getRowProps({ row })}>
                          {row.cells.map((cell) => {
                            if (cell.info.header === "Status") {
                              const status = cell.value as BackupStatus;
                              return (
                                <TableCell key={cell.id}>
                                  <Tag type={statusTagType(status)} size="sm">
                                    {status}
                                  </Tag>
                                </TableCell>
                              );
                            }
                            if (cell.info.header === "Actions") {
                              return (
                                <TableCell key={cell.id}>
                                  <div style={{ display: "flex", gap: "var(--frost-gap-row)" }}>
                                    {backup.status === "completed" && (
                                      <BracketButton
                                        kind="ghost"
                                        size="sm"
                                        onClick={(e) => {
                                          e.stopPropagation();
                                          window.open(getBackupDownloadUrl(backup.id), "_blank");
                                        }}
                                      >
                                        Download
                                      </BracketButton>
                                    )}
                                    <BracketButton
                                      kind="danger--ghost"
                                      size="sm"
                                      onClick={(e) => {
                                        e.stopPropagation();
                                        setDeleteTarget(backup);
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

      {/* Schedule configuration */}
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          gap: "var(--frost-gap-row)",
        }}
      >
        <p style={sectionLabelStyle}>§ BACKUP SCHEDULE</p>

        {scheduleQuery.isLoading && (
          <p
            style={{
              fontFamily: "var(--frost-font-mono)",
              fontSize: "var(--frost-type-mono-body-size)",
              color: "color-mix(in oklch, var(--frost-ink) 55%, transparent)",
              margin: 0,
            }}
          >
            Loading schedule...
          </p>
        )}
        {scheduleQuery.error && (
          <QueryErrorNotification error={scheduleQuery.error} title="Failed to load schedule" />
        )}

        {schedule && (
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--frost-gap-row)", maxWidth: "var(--frost-strip-3)" }}>
            <Toggle
              id="backup-schedule-enabled"
              labelText="Automatic backups"
              labelA="Disabled"
              labelB="Enabled"
              toggled={schedule.backupEnabled ?? false}
              onToggle={() => {
                handleToggleEnabled(!(schedule.backupEnabled ?? false));
              }}
              disabled={updateScheduleMutation.isPending}
            />

            <MonoSelect
              id="backup-frequency"
              labelText="Frequency"
              value={schedule.backupFrequency ?? "weekly"}
              onChange={(e) => handleFrequencyChange(e.target.value)}
              disabled={updateScheduleMutation.isPending || !(schedule.backupEnabled ?? false)}
            >
              <MonoSelectItem value="daily" text="Daily" />
              <MonoSelectItem value="weekly" text="Weekly" />
            </MonoSelect>

            <NumberInput
              id="backup-retention"
              label="Retention count"
              value={schedule.backupRetentionCount ?? 5}
              min={1}
              max={100}
              step={1}
              onChange={(_event: unknown, { value }: { value: number | string }) => {
                handleRetentionChange(Number(value));
              }}
              disabled={updateScheduleMutation.isPending || !(schedule.backupEnabled ?? false)}
            />
          </div>
        )}
      </div>

      {/* Restore section */}
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          gap: "var(--frost-gap-row)",
        }}
      >
        <p style={sectionLabelStyle}>§ RESTORE</p>
        <RestoreUpload />
      </div>

      {/* Delete confirmation */}
      <BrutalistModal
        open={deleteTarget != null}
        danger
        onRequestClose={() => {
          if (!deleteMutation.isPending) setDeleteTarget(null);
        }}
        onRequestSubmit={handleDelete}
      >
        <BrutalistModalHeader title="Delete backup" />
        <BrutalistModalBody>
          <p
            style={{
              fontFamily: "var(--frost-font-mono)",
              fontSize: "var(--frost-type-mono-body-size)",
              color: "var(--frost-ink)",
              margin: 0,
            }}
          >
            {deleteTarget
              ? `Delete backup #${deleteTarget.id}? This action cannot be undone.`
              : "Delete selected backup?"}
          </p>
        </BrutalistModalBody>
        <BrutalistModalFooter
          primaryButtonText={deleteMutation.isPending ? "Deleting..." : "Delete"}
          secondaryButtonText="Cancel"
          onRequestClose={() => {
            if (!deleteMutation.isPending) setDeleteTarget(null);
          }}
          onRequestSubmit={handleDelete}
        />
      </BrutalistModal>
    </main>
  );
}
