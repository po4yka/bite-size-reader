import {
  InlineLoading,
  ProgressBar,
  Tag,
  UnorderedList,
  ListItem,
} from "@carbon/react";
import { useImportJob } from "../../hooks/useImportExport";

function statusTagType(status: string): "green" | "blue" | "red" | "warm-gray" {
  if (status === "completed") return "green";
  if (status === "processing") return "blue";
  if (status === "failed") return "red";
  return "warm-gray";
}

interface ImportJobStatusProps {
  jobId: number;
}

export default function ImportJobStatus({ jobId }: ImportJobStatusProps) {
  const { data: job, isLoading, error } = useImportJob(jobId);

  if (isLoading) return <InlineLoading description="Loading job status..." />;
  if (error || !job) return null;

  const progressValue = job.totalItems > 0
    ? (job.processedItems / job.totalItems) * 100
    : 0;

  return (
    <div style={{ marginTop: "1rem" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.5rem" }}>
        <h4>Import Job #{job.id}</h4>
        <Tag type={statusTagType(job.status)} size="sm">
          {job.status}
        </Tag>
      </div>

      {job.totalItems > 0 && (
        <ProgressBar
          label={`${job.processedItems} / ${job.totalItems} items`}
          value={progressValue}
          max={100}
        />
      )}

      <p style={{ margin: "0.5rem 0", fontSize: "0.875rem" }}>
        Created: {job.createdItems} | Skipped: {job.skippedItems} | Failed: {job.failedItems}
      </p>

      {job.failedItems > 0 && job.errors.length > 0 && (
        <details style={{ marginTop: "0.5rem" }}>
          <summary style={{ cursor: "pointer", fontSize: "0.875rem", color: "var(--cds-text-error)" }}>
            {job.errors.length} error(s)
          </summary>
          <UnorderedList style={{ marginTop: "0.25rem", fontSize: "0.8125rem" }}>
            {job.errors.map((err, i) => (
              <ListItem key={i}>
                <strong>{err.url}</strong>: {err.error}
              </ListItem>
            ))}
          </UnorderedList>
        </details>
      )}
    </div>
  );
}
