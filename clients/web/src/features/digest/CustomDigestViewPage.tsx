import { useParams } from "react-router-dom";
import { InlineLoading, InlineNotification, Tag, Tile } from "../../design";
import { useCustomDigest } from "../../hooks/useDigest";

export default function CustomDigestViewPage() {
  const { id } = useParams<{ id: string }>();
  const digestId = Number(id ?? "0");

  const { data: digest, isLoading, error } = useCustomDigest(digestId);

  if (isLoading) {
    return (
      <section className="page-section">
        <InlineLoading description="Loading custom digest..." />
      </section>
    );
  }

  if (error || !digest) {
    return (
      <section className="page-section">
        <InlineNotification
          kind="error"
          title="Failed to load digest"
          subtitle={error instanceof Error ? error.message : "Digest not found."}
          hideCloseButton
        />
      </section>
    );
  }

  const channelMap = new Map(digest.channels.map((c) => [c.id, c.title || `@${c.username}`]));

  return (
    <section className="page-section">
      <h1>{digest.title}</h1>
      <p>Created: {new Date(digest.createdAt).toLocaleString()}</p>

      <Tile style={{ marginTop: "1rem", marginBottom: "1rem" }}>
        <h3>Channels</h3>
        <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem", marginTop: "0.5rem" }}>
          {digest.channels.map((channel) => (
            <Tag key={channel.id} type="blue">
              {channel.title || `@${channel.username}`}
            </Tag>
          ))}
          {digest.channels.length === 0 && <p>No channels.</p>}
        </div>
      </Tile>

      <Tile>
        <h3>Posts ({digest.posts.length})</h3>
        {digest.posts.length === 0 && (
          <p style={{ marginTop: "0.5rem" }}>No posts in this digest.</p>
        )}
        {digest.posts.map((post) => (
          <div
            key={post.id}
            style={{ borderBottom: "1px solid #e0e0e0", padding: "1rem 0" }}
          >
            <Tag type="warm-gray">{channelMap.get(post.channelId) ?? `Channel ${post.channelId}`}</Tag>
            <p style={{ marginTop: "0.5rem", whiteSpace: "pre-wrap" }}>{post.text}</p>
            <span style={{ fontSize: "0.75rem", color: "#6f6f6f" }}>
              {new Date(post.createdAt).toLocaleString()}
            </span>
          </div>
        ))}
      </Tile>
    </section>
  );
}
