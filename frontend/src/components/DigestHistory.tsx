import { useCallback, useEffect, useState } from "react";
import { fetchHistory, type HistoryData } from "../api/digest";

export default function DigestHistory() {
  const [data, setData] = useState<HistoryData | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(0);
  const pageSize = 20;

  const load = useCallback(async () => {
    try {
      setError("");
      setLoading(true);
      const result = await fetchHistory(pageSize, page * pageSize);
      setData(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load history");
    } finally {
      setLoading(false);
    }
  }, [page]);

  useEffect(() => {
    load();
  }, [load]);

  if (loading && !data) return <div className="loading">Loading history...</div>;
  if (error) return <div className="error">{error}</div>;
  if (!data) return null;

  const totalPages = Math.ceil(data.total / pageSize);

  return (
    <div className="digest-history">
      {data.deliveries.length === 0 ? (
        <p className="empty">No digest deliveries yet.</p>
      ) : (
        <>
          <ul className="history-list">
            {data.deliveries.map((d) => (
              <li key={d.id} className="history-item">
                <div className="history-date">
                  {new Date(d.delivered_at).toLocaleDateString(undefined, {
                    month: "short",
                    day: "numeric",
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                </div>
                <div className="history-details">
                  <span>{d.post_count} posts</span>
                  <span>{d.channel_count} channels</span>
                  <span className="digest-type">{d.digest_type}</span>
                </div>
              </li>
            ))}
          </ul>

          {totalPages > 1 && (
            <div className="pagination">
              <button
                disabled={page === 0 || loading}
                onClick={() => setPage((p) => p - 1)}
              >
                Previous
              </button>
              <span>
                {page + 1} / {totalPages}
              </span>
              <button
                disabled={page >= totalPages - 1 || loading}
                onClick={() => setPage((p) => p + 1)}
              >
                Next
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
