import {
  MonoProgressBar,
  SparkLoading,
  Tag,
  UnorderedList,
  ListItem,
} from "../../design";
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

  if (isLoading) return <SparkLoading description="Loading job status..." />;
  if (error || !job) return null;

  const progressValue = job.totalItems > 0
    ? (job.processedItems / job.totalItems) * 100
    : 0;

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "var(--frost-gap-row)",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: "var(--frost-gap-row)" }}>
        <h4
          style={{
            fontFamily: "var(--frost-font-mono)",
            fontSize: "var(--frost-type-mono-body-size)",
            fontWeight: "var(--frost-type-mono-emph-weight)" as React.CSSProperties["fontWeight"],
            color: "var(--frost-ink)",
            margin: 0,
          }}
        >
          Import Job #{job.id}
        </h4>
        <Tag type={statusTagType(job.status)} size="sm">
          {job.status}
        </Tag>
      </div>

      {job.totalItems > 0 && (
        <MonoProgressBar
          label={`${job.processedItems} / ${job.totalItems} items`}
          value={progressValue}
          max={100}
        />
      )}

      <p
        style={{
          fontFamily: "var(--frost-font-mono)",
          fontSize: "var(--frost-type-mono-xs-size)",
          color: "color-mix(in oklch, var(--frost-ink) 55%, transparent)",
          margin: 0,
        }}
      >
        Created: {job.createdItems} | Skipped: {job.skippedItems} | Failed: {job.failedItems}
      </p>

      {job.failedItems > 0 && job.errors.length > 0 && (
        <details>
          <summary
            style={{
              cursor: "pointer",
              fontFamily: "var(--frost-font-mono)",
              fontSize: "var(--frost-type-mono-xs-size)",
              color: "var(--frost-spark)",
            }}
          >
            {job.errors.length} error(s)
          </summary>
          <UnorderedList style={{ marginTop: "0.25rem" }}>
            {job.errors.map((err, i) => (
              <ListItem
                key={i}
                style={{
                  fontFamily: "var(--frost-font-mono)",
                  fontSize: "var(--frost-type-mono-xs-size)",
                  color: "var(--frost-ink)",
                }}
              >
                <strong>{err.url}</strong>: {err.error}
              </ListItem>
            ))}
          </UnorderedList>
        </details>
      )}
    </div>
  );
}
