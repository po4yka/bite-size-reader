import { SkeletonText, Tag, Tile } from "../../design";
import { useReadingStreak } from "../../hooks/useUser";
import { QueryErrorNotification } from "../../components/QueryErrorNotification";

function formatDate(dateStr: string | null): string {
  if (!dateStr) return "Never";
  return new Date(dateStr).toLocaleString();
}

export default function ReadingStreakSection() {
  const streakQuery = useReadingStreak();

  return (
    <Tile>
      <h3 style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "1rem" }}>
        Reading Streak
        {streakQuery.data && (
          <Tag type="warm-gray" size="md">
            {streakQuery.data.currentStreak} days
          </Tag>
        )}
      </h3>

      <QueryErrorNotification error={streakQuery.error} title="Failed to load streak" />

      {streakQuery.isLoading && !streakQuery.data && (
        <SkeletonText paragraph lineCount={4} />
      )}

      {streakQuery.data && (
        <>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(4, 1fr)",
              gap: "1rem",
              marginBottom: "1rem",
            }}
          >
            <div>
              <p style={{ fontSize: "0.75rem", color: "var(--rtk-color-text-muted, var(--cds-text-secondary))" }}>Current streak</p>
              <p style={{ fontSize: "1.5rem", fontWeight: 600 }}>{streakQuery.data.currentStreak} days</p>
            </div>
            <div>
              <p style={{ fontSize: "0.75rem", color: "var(--rtk-color-text-muted, var(--cds-text-secondary))" }}>Longest streak</p>
              <p style={{ fontSize: "1.5rem", fontWeight: 600 }}>{streakQuery.data.longestStreak} days</p>
            </div>
            <div>
              <p style={{ fontSize: "0.75rem", color: "var(--rtk-color-text-muted, var(--cds-text-secondary))" }}>This week</p>
              <p style={{ fontSize: "1.5rem", fontWeight: 600 }}>{streakQuery.data.weekCount}</p>
            </div>
            <div>
              <p style={{ fontSize: "0.75rem", color: "var(--rtk-color-text-muted, var(--cds-text-secondary))" }}>This month</p>
              <p style={{ fontSize: "1.5rem", fontWeight: 600 }}>{streakQuery.data.monthCount}</p>
            </div>
          </div>
          <p style={{ fontSize: "0.75rem", color: "var(--rtk-color-text-muted, var(--cds-text-secondary))" }}>
            Last read: {formatDate(streakQuery.data.lastActivityDate)}
          </p>
        </>
      )}
    </Tile>
  );
}
