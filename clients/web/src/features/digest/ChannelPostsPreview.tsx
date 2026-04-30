import { SparkLoading, StatusBadge, Tag } from "../../design";
import type { DigestChannelPost } from "../../api/digest";
import { useChannelPosts } from "../../hooks/useDigest";

export function ChannelPostsPreview({ username }: { username: string }) {
  const postsQuery = useChannelPosts(username);

  if (postsQuery.isLoading) {
    return <SparkLoading description="Loading posts..." />;
  }

  if (postsQuery.error) {
    return (
      <StatusBadge severity="alarm" title="Failed to load posts">
        {postsQuery.error instanceof Error ? postsQuery.error.message : "Unknown error"}
      </StatusBadge>
    );
  }

  const posts: DigestChannelPost[] = postsQuery.data?.posts ?? [];

  if (posts.length === 0) {
    return <p className="muted">No recent posts found.</p>;
  }

  return (
    <ul className="digest-list">
      {posts.map((post) => (
        <li
          key={post.id}
          style={{
            padding: "0.5rem 0",
            borderBottom: "1px solid var(--rtk-color-border-subtle)",
          }}
        >
          <div className="digest-list-item-row">
            <span className="muted digest-text-xs">
              {new Date(post.date).toLocaleString()}
            </span>
            <Tag size="sm">
              {post.contentType}
            </Tag>
            {post.views != null && (
              <span className="muted digest-text-xs">
                {post.views} views
              </span>
            )}
          </div>
          <p style={{ margin: 0, fontSize: "0.875rem" }}>
            {post.text ? (post.text.length > 200 ? `${post.text.slice(0, 200)}...` : post.text) : "(no text)"}
          </p>
        </li>
      ))}
    </ul>
  );
}
