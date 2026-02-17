import { useCallback, useEffect, useState } from "react";
import { fetchUserStats } from "../../api/user";
import type { UserStats } from "../../types/api";
import LoadingSpinner from "../common/LoadingSpinner";
import ErrorBanner from "../common/ErrorBanner";

function formatReadingTime(minutes: number): string {
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  const remaining = minutes % 60;
  return remaining > 0 ? `${hours}h ${remaining}m` : `${hours}h`;
}

interface HorizontalBarProps {
  label: string;
  value: number;
  maxValue: number;
}

function HorizontalBar({ label, value, maxValue }: HorizontalBarProps) {
  const widthPct = maxValue > 0 ? Math.round((value / maxValue) * 100) : 0;

  return (
    <div className="stat-bar">
      <div className="stat-bar-header">
        <span className="stat-bar-label">{label}</span>
        <span className="stat-bar-value">{value}</span>
      </div>
      <div className="stat-bar-track">
        <div className="stat-bar-fill" style={{ width: `${widthPct}%` }} />
      </div>
    </div>
  );
}

export default function UserStatsView() {
  const [stats, setStats] = useState<UserStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      setError("");
      setLoading(true);
      const result = await fetchUserStats();
      setStats(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load stats");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (loading) return <LoadingSpinner text="Loading stats..." />;
  if (error) return <ErrorBanner message={error} onRetry={load} />;
  if (!stats) return null;

  const topicMax = stats.top_topics.length > 0 ? stats.top_topics[0].count : 1;
  const domainMax = stats.top_domains.length > 0 ? stats.top_domains[0].count : 1;

  return (
    <div className="user-stats">
      <div className="stat-grid">
        <div className="stat-card">
          <span className="stat-card-value">{stats.total_summaries}</span>
          <span className="stat-card-label">Total Summaries</span>
        </div>
        <div className="stat-card">
          <span className="stat-card-value">
            {formatReadingTime(stats.total_reading_time_min)}
          </span>
          <span className="stat-card-label">Reading Time</span>
        </div>
        <div className="stat-card">
          <span className="stat-card-value">{stats.summaries_this_week}</span>
          <span className="stat-card-label">This Week</span>
        </div>
        <div className="stat-card">
          <span className="stat-card-value">{stats.summaries_this_month}</span>
          <span className="stat-card-label">This Month</span>
        </div>
      </div>

      {stats.top_topics.length > 0 && (
        <div className="stat-section">
          <h3 className="stat-section-title">Top Topics</h3>
          {stats.top_topics.map((topic) => (
            <HorizontalBar
              key={topic.tag}
              label={topic.tag}
              value={topic.count}
              maxValue={topicMax}
            />
          ))}
        </div>
      )}

      {stats.top_domains.length > 0 && (
        <div className="stat-section">
          <h3 className="stat-section-title">Top Domains</h3>
          {stats.top_domains.map((domain) => (
            <HorizontalBar
              key={domain.domain}
              label={domain.domain}
              value={domain.count}
              maxValue={domainMax}
            />
          ))}
        </div>
      )}
    </div>
  );
}
