import type { SyntheticEvent } from "react";
import { useState } from "react";
import { FileUploader, InlineLoading, InlineNotification } from "@carbon/react";
import { useRestoreBackup } from "../../hooks/useBackups";
import type { RestoreResult } from "../../api/backups";

export default function RestoreUpload() {
  const restoreMutation = useRestoreBackup();
  const [result, setResult] = useState<RestoreResult | null>(null);

  function handleChange(event: SyntheticEvent<HTMLElement>): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) return;

    setResult(null);
    restoreMutation.mutate(file, {
      onSuccess: (data) => {
        setResult(data);
      },
    });
  }

  return (
    <div style={{ marginTop: "1rem" }}>
      <FileUploader
        labelTitle="Restore from backup"
        labelDescription="Upload a backup ZIP file to restore your data"
        buttonLabel="Choose file"
        accept={[".zip"]}
        onChange={handleChange}
        disabled={restoreMutation.isPending}
        filenameStatus={restoreMutation.isPending ? "uploading" : "edit"}
      />

      {restoreMutation.isPending && (
        <InlineLoading description="Restoring..." style={{ marginTop: "0.5rem" }} />
      )}

      {restoreMutation.error && (
        <InlineNotification
          kind="error"
          title="Restore failed"
          subtitle={(restoreMutation.error as Error).message}
          hideCloseButton
          style={{ marginTop: "0.5rem" }}
        />
      )}

      {result && (
        <InlineNotification
          kind={result.errors.length > 0 ? "warning" : "success"}
          title="Restore complete"
          subtitle={formatRestoreResult(result)}
          hideCloseButton
          style={{ marginTop: "0.5rem" }}
        />
      )}
    </div>
  );
}

function formatRestoreResult(result: RestoreResult): string {
  const parts: string[] = [];
  for (const [key, count] of Object.entries(result.restored)) {
    if (count > 0) parts.push(`${count} ${key}`);
  }
  const restored = parts.length > 0 ? `Restored: ${parts.join(", ")}` : "No new items restored";

  const skippedParts: string[] = [];
  for (const [key, count] of Object.entries(result.skipped)) {
    if (count > 0) skippedParts.push(`${count} ${key}`);
  }
  const skipped = skippedParts.length > 0 ? `. Skipped: ${skippedParts.join(", ")}` : "";

  const errors = result.errors.length > 0 ? `. Errors: ${result.errors.length}` : "";

  return `${restored}${skipped}${errors}`;
}
