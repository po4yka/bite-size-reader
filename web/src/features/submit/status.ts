import type { RequestStatus } from "../../api/types";

export function isTerminalStatus(status: RequestStatus["status"]): boolean {
  return status === "completed" || status === "failed";
}

export function progressFromStatus(status: RequestStatus["status"], progressPct: number): number {
  if (status === "completed") return 100;
  if (status === "failed") return Math.max(0, Math.min(100, progressPct));
  if (progressPct > 0) return Math.max(0, Math.min(95, progressPct));

  if (status === "pending") return 10;
  if (status === "crawling") return 40;
  if (status === "processing") return 70;
  return 0;
}

export function statusLabel(status: RequestStatus["status"]): string {
  if (status === "pending") return "Waiting in queue";
  if (status === "crawling") return "Extracting content";
  if (status === "processing") return "Generating summary";
  if (status === "completed") return "Completed";
  return "Failed";
}

export function formatEta(estimatedSecondsRemaining?: number | null): string | null {
  if (!estimatedSecondsRemaining || estimatedSecondsRemaining <= 0) return null;
  if (estimatedSecondsRemaining < 60) {
    return `~${estimatedSecondsRemaining}s remaining`;
  }
  const minutes = Math.ceil(estimatedSecondsRemaining / 60);
  return `~${minutes}m remaining`;
}
