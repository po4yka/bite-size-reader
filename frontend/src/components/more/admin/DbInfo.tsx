import { useCallback, useEffect, useState } from "react";
import { fetchDbInfo, type DbInfo as DbInfoData } from "../../../api/admin";

export default function DbInfo() {
  const [data, setData] = useState<DbInfoData | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      setError("");
      const result = await fetchDbInfo();
      setData(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load DB info");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (loading) return <div className="loading">Loading database info...</div>;
  if (error) return <div className="error">{error}</div>;
  if (!data) return null;

  const totalRows = Object.values(data.table_counts).reduce(
    (sum, count) => sum + (count > 0 ? count : 0),
    0,
  );

  return (
    <div className="admin-section">
      <h3 className="admin-section-title">Database</h3>

      <div className="db-summary">
        <div className="db-stat">
          <span className="db-stat-value">{data.file_size_mb} MB</span>
          <span className="db-stat-label">File Size</span>
        </div>
        <div className="db-stat">
          <span className="db-stat-value">{totalRows.toLocaleString()}</span>
          <span className="db-stat-label">Total Rows</span>
        </div>
        <div className="db-stat">
          <span className="db-stat-value">
            {Object.keys(data.table_counts).length}
          </span>
          <span className="db-stat-label">Tables</span>
        </div>
      </div>

      <div className="db-tables">
        {Object.entries(data.table_counts).map(([table, count]) => (
          <div key={table} className="db-table-row">
            <span className="db-table-name">{table}</span>
            <span className="db-table-count">
              {count >= 0 ? count.toLocaleString() : "error"}
            </span>
          </div>
        ))}
      </div>

      <div className="db-path">
        <span className="db-path-label">Path:</span> {data.db_path}
      </div>
    </div>
  );
}
