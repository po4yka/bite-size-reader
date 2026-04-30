import { useParams } from "react-router-dom";
import { BrutalistCard, BrutalistSkeletonPlaceholder, BrutalistSkeletonText, SparkLoading, StatusBadge, Tag } from "../../design";
import { useCustomDigest } from "../../hooks/useDigest";

export default function CustomDigestViewPage() {
  const { id } = useParams<{ id: string }>();
  const digestId = Number(id ?? "0");

  const { data: digest, isLoading, error } = useCustomDigest(digestId);

  if (isLoading) {
    return (
      <section
        className="page-section"
        style={{
          maxWidth: "var(--frost-strip-7, 1232px)",
          padding: "var(--frost-pad-page, 32px)",
        }}
      >
        <BrutalistSkeletonText heading width="40%" />
        <BrutalistSkeletonText paragraph lineCount={2} />
        <BrutalistSkeletonPlaceholder style={{ width: "100%", height: "200px", marginTop: "1rem" }} />
        <SparkLoading description="Loading custom digest..." />
      </section>
    );
  }

  if (error || !digest) {
    return (
      <section
        className="page-section"
        style={{
          maxWidth: "var(--frost-strip-7, 1232px)",
          padding: "var(--frost-pad-page, 32px)",
        }}
      >
        <StatusBadge severity="alarm" title="Failed to load digest">
          {error instanceof Error ? error.message : "Digest not found."}
        </StatusBadge>
      </section>
    );
  }

  const channelMap = new Map(digest.channels.map((c) => [c.id, c.title || `@${c.username}`]));

  return (
    <section
      className="page-section"
      style={{
        maxWidth: "var(--frost-strip-7, 1232px)",
        padding: "var(--frost-pad-page, 32px)",
        display: "flex",
        flexDirection: "column",
        gap: "var(--frost-gap-section, 48px)",
      }}
    >
      <h1>{digest.title}</h1>
      <p>Created: {new Date(digest.createdAt).toLocaleString()}</p>

      <BrutalistCard>
        <h3>Channels</h3>
        <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem", marginTop: "0.5rem" }}>
          {digest.channels.map((channel) => (
            <Tag key={channel.id} type="blue">
              {channel.title || `@${channel.username}`}
            </Tag>
          ))}
          {digest.channels.length === 0 && <p>No channels.</p>}
        </div>
      </BrutalistCard>

      <BrutalistCard>
        <h3>Posts ({digest.posts.length})</h3>
        {digest.posts.length === 0 && (
          <p style={{ marginTop: "0.5rem" }}>No posts in this digest.</p>
        )}
        {digest.posts.map((post) => (
          <div
            key={post.id}
            style={{
              borderBottom: `1px solid color-mix(in oklch, var(--frost-ink) 25%, transparent)`,
              padding: "1rem 0",
            }}
          >
            <Tag type="warm-gray">{channelMap.get(post.channelId) ?? `Channel ${post.channelId}`}</Tag>
            <p style={{ marginTop: "0.5rem", whiteSpace: "pre-wrap" }}>{post.text}</p>
            <span style={{ fontSize: "0.75rem", color: "color-mix(in oklch, var(--frost-ink) 60%, transparent)" }}>
              {new Date(post.createdAt).toLocaleString()}
            </span>
          </div>
        ))}
      </BrutalistCard>
    </section>
  );
}
