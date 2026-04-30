import { BrutalistCard, BrutalistSkeletonPlaceholder } from "../../design";
import { QueryErrorNotification } from "../../components/QueryErrorNotification";
import { useAdminJobs } from "../../hooks/useAdmin";

const ALARM = "var(--frost-spark)";

function StatCard({ label, value, kind }: { label: string; value: number; kind?: "danger" }) {
  return (
    <BrutalistCard style={{ textAlign: "center", minWidth: 140 }}>
      <p className="rtk-label">{label}</p>
      <p
        style={{
          fontSize: "1.75rem",
          fontWeight: 600,
          color: kind === "danger" && value > 0 ? ALARM : undefined,
        }}
      >
        {value.toLocaleString()}
      </p>
    </BrutalistCard>
  );
}

export default function AdminJobs() {
  const { data, isLoading, error } = useAdminJobs();

  if (isLoading) {
    return (
      <div style={{ display: "flex", gap: "1rem", flexWrap: "wrap" }}>
        {Array.from({ length: 4 }, (_, i) => (
          <BrutalistSkeletonPlaceholder key={i} style={{ width: 140, height: 80 }} />
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
            <StatCard label="Pending" value={data.pipeline.pending} />
            <StatCard label="Processing" value={data.pipeline.processing} />
            <StatCard label="Completed today" value={data.pipeline.completedToday} />
            <StatCard label="Failed today" value={data.pipeline.failedToday} kind="danger" />
          </div>

          <h4 style={{ marginBottom: "0.75rem" }}>Import Jobs</h4>
          <div style={{ display: "flex", gap: "1rem", flexWrap: "wrap" }}>
            <StatCard label="Active" value={data.imports.active} />
            <StatCard label="Completed today" value={data.imports.completedToday} />
          </div>
        </>
      )}
    </>
  );
}
