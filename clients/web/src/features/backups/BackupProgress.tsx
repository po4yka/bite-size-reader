import { InlineLoading } from "@carbon/react";
import { useBackupPolling } from "../../hooks/useBackups";
import type { BackupStatus } from "../../api/backups";

interface BackupProgressProps {
  backupId: number;
  onComplete: () => void;
}

export default function BackupProgress({ backupId, onComplete }: BackupProgressProps) {
  const { data } = useBackupPolling(backupId, true);

  const status: BackupStatus | undefined = data?.status;

  if (status === "completed" || status === "failed") {
    // Notify parent that processing finished
    onComplete();
  }

  if (status === "failed") {
    return <InlineLoading status="error" description={`Backup failed: ${data?.error ?? "unknown error"}`} />;
  }

  if (status === "completed") {
    return <InlineLoading status="finished" description="Backup completed" />;
  }

  return <InlineLoading description="Creating backup..." />;
}
