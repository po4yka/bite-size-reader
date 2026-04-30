import { BrutalistCard, BrutalistSkeletonText, Tag } from "../../design";
import { useReadingStreak } from "../../hooks/useUser";
import { QueryErrorNotification } from "../../components/QueryErrorNotification";

const MUTED = "color-mix(in oklch, var(--frost-ink) 55%, transparent)";

function formatDate(dateStr: string | null): string {
  if (!dateStr) return "Never";
  return new Date(dateStr).toLocaleString();
}

export default function ReadingStreakSection() {
  const streakQuery = useReadingStreak();

  return (
    <BrutalistCard>
      <p
        style={{
          fontFamily: "var(--frost-font-mono)",
          fontSize: "11px",
          fontWeight: 800,
          textTransform: "uppercase",
          letterSpacing: "1px",
          color: MUTED,
          marginBottom: "1rem",
          display: "flex",
          alignItems: "center",
          gap: "0.5rem",
        }}
      >
        § Reading Streak
        {streakQuery.data && (
          <Tag size="md">
            {streakQuery.data.currentStreak} days
          </Tag>
        )}
      </p>

      <QueryErrorNotification error={streakQuery.error} title="Failed to load streak" />

      {streakQuery.isLoading && !streakQuery.data && (
        <BrutalistSkeletonText paragraph lineCount={4} />
      )}

      {streakQuery.data && (
        <>
          <div
            className="reading-streak-grid"
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(4, 1fr)",
              gap: "1rem",
              marginBottom: "1rem",
            }}
          >
            <div>
              <p style={{ fontSize: "0.75rem", color: MUTED }}>Current streak</p>
              <p style={{ fontSize: "1.5rem", fontWeight: 600 }}>{streakQuery.data.currentStreak} days</p>
            </div>
            <div>
              <p style={{ fontSize: "0.75rem", color: MUTED }}>Longest streak</p>
              <p style={{ fontSize: "1.5rem", fontWeight: 600 }}>{streakQuery.data.longestStreak} days</p>
            </div>
            <div>
              <p style={{ fontSize: "0.75rem", color: MUTED }}>This week</p>
              <p style={{ fontSize: "1.5rem", fontWeight: 600 }}>{streakQuery.data.weekCount}</p>
            </div>
            <div>
              <p style={{ fontSize: "0.75rem", color: MUTED }}>This month</p>
              <p style={{ fontSize: "1.5rem", fontWeight: 600 }}>{streakQuery.data.monthCount}</p>
            </div>
          </div>
          <p style={{ fontSize: "0.75rem", color: MUTED }}>
            Last read: {formatDate(streakQuery.data.lastActivityDate)}
          </p>
        </>
      )}
    </BrutalistCard>
  );
}
