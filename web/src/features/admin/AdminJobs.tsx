import { SkeletonPlaceholder, Tile } from "@carbon/react";
import { QueryErrorNotification } from "../../components/QueryErrorNotification";
import { useAdminJobs } from "../../hooks/useAdmin";

function StatTile({ label, value, kind }: { label: string; value: number; kind?: "danger" }) {
  return (
    <Tile style={{ textAlign: "center", minWidth: 140 }}>
      <p className="cds--label">{label}</p>
      <p style={{ fontSize: "1.75rem", fontWeight: 600, color: kind === "danger" && value > 0 ? "var(--cds-support-error)" : undefined }}>
        {value.toLocaleString()}
      </p>
    </Tile>
  );
}

export default function AdminJobs() {
  const { data, isLoading, error } = useAdminJobs();

  if (isLoading) {
    return (
      <div style={{ display: "flex", gap: "1rem", flexWrap: "wrap" }}>
        {Array.from({ length: 4 }, (_, i) => (
          <SkeletonPlaceholder key={i} style={{ width: 140, height: 80 }} />
        ))}
      </div>
    );
  }

  return (
    <>
      <QueryErrorNotification error={error} title="Failed to load job status" />

      {data && (
        <>
          <h4 style={{ marginBottom: "0.75rem" }}>Pipeline</h4>
          <div style={{ display: "flex", gap: "1rem", flexWrap: "wrap", marginBottom: "1.5rem" }}>
            <StatTile label="Pending" value={data.pipeline.pending} />
            <StatTile label="Processing" value={data.pipeline.processing} />
            <StatTile label="Completed today" value={data.pipeline.completedToday} />
            <StatTile label="Failed today" value={data.pipeline.failedToday} kind="danger" />
          </div>

          <h4 style={{ marginBottom: "0.75rem" }}>Import Jobs</h4>
          <div style={{ display: "flex", gap: "1rem", flexWrap: "wrap" }}>
            <StatTile label="Active" value={data.imports.active} />
            <StatTile label="Completed today" value={data.imports.completedToday} />
          </div>
        </>
      )}
    </>
  );
}
