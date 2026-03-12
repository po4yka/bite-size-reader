import { useCallback, useEffect, useState } from "react";
import {
  fetchChannels,
  subscribeChannel,
  unsubscribeChannel,
  triggerDigest,
  resolveChannel,
  fetchChannelPosts,
  listCategories,
  assignCategory,
  bulkUnsubscribe,
  bulkAssignCategory,
  type ChannelsData,
  type ChannelSubscription,
  type ResolvedChannel,
  type ChannelPost,
  type Category,
} from "../api/digest";
import { useToast } from "../hooks/useToast";

interface ExpandedPostsState {
  posts: ChannelPost[];
  loading: boolean;
}

export default function ChannelList() {
  const { addToast } = useToast();
  const [data, setData] = useState<ChannelsData | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [input, setInput] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [triggering, setTriggering] = useState(false);

  // Resolve-before-subscribe state
  const [resolving, setResolving] = useState(false);
  const [preview, setPreview] = useState<ResolvedChannel | null>(null);

  // Post preview state: keyed by channel username
  const [expandedChannels, setExpandedChannels] = useState<
    Record<string, ExpandedPostsState>
  >({});

  // Category state
  const [categories, setCategories] = useState<Category[]>([]);

  // Bulk selection state
  const [selected, setSelected] = useState<Set<number>>(new Set());

  const load = useCallback(async () => {
    try {
      setError("");
      const result = await fetchChannels();
      setData(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load channels");
    } finally {
      setLoading(false);
    }
  }, []);

  const loadCategories = useCallback(async () => {
    try {
      const cats = await listCategories();
      setCategories(cats);
    } catch {
      // Categories are optional; fail silently
    }
  }, []);

  useEffect(() => {
    load();
    loadCategories();
  }, [load, loadCategories]);

  // --- Resolve before subscribe ---

  const handlePreview = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || resolving) return;
    setResolving(true);
    setPreview(null);
    try {
      const resolved = await resolveChannel(input.trim());
      setPreview(resolved);
    } catch {
      // Resolve failed -- fall back to direct subscribe
      await doSubscribe(input.trim());
    } finally {
      setResolving(false);
    }
  };

  const doSubscribe = async (username: string) => {
    setSubmitting(true);
    try {
      const result = await subscribeChannel(username);
      addToast(`Subscribed to @${result.username}`, "success");
      setInput("");
      setPreview(null);
      await load();
    } catch (err) {
      addToast(
        err instanceof Error ? err.message : "Subscribe failed",
        "error",
      );
    } finally {
      setSubmitting(false);
    }
  };

  const handleConfirmSubscribe = async () => {
    if (!preview || submitting) return;
    await doSubscribe(preview.username);
  };

  const handleCancelPreview = () => {
    setPreview(null);
  };

  // --- Unsubscribe ---

  const handleUnsubscribe = async (username: string) => {
    if (submitting) return;

    const confirmed = await new Promise<boolean>((resolve) => {
      const wa = window.Telegram?.WebApp;
      if (wa?.showConfirm) {
        wa.showConfirm(`Unsubscribe from @${username}?`, resolve);
      } else {
        resolve(window.confirm(`Unsubscribe from @${username}?`));
      }
    });
    if (!confirmed) return;

    window.Telegram?.WebApp?.HapticFeedback?.impactOccurred("heavy");
    setSubmitting(true);
    try {
      await unsubscribeChannel(username);
      addToast(`Unsubscribed from @${username}`, "success");
      await load();
    } catch (err) {
      addToast(
        err instanceof Error ? err.message : "Unsubscribe failed",
        "error",
      );
    } finally {
      setSubmitting(false);
    }
  };

  // --- Trigger digest ---

  const handleTrigger = async () => {
    if (triggering) return;
    setTriggering(true);
    try {
      await triggerDigest();
      addToast("Digest queued! Check your Telegram chat.", "success");
    } catch (err) {
      addToast(
        err instanceof Error ? err.message : "Trigger failed",
        "error",
      );
    } finally {
      setTriggering(false);
    }
  };

  // --- Post preview (expandable channels) ---

  const toggleChannelPosts = async (username: string) => {
    if (expandedChannels[username]) {
      setExpandedChannels((prev) => {
        const next = { ...prev };
        delete next[username];
        return next;
      });
      return;
    }

    setExpandedChannels((prev) => ({
      ...prev,
      [username]: { posts: [], loading: true },
    }));

    try {
      const result = await fetchChannelPosts(username);
      setExpandedChannels((prev) => ({
        ...prev,
        [username]: { posts: result.posts, loading: false },
      }));
    } catch {
      setExpandedChannels((prev) => ({
        ...prev,
        [username]: { posts: [], loading: false },
      }));
      addToast(`Failed to load posts for @${username}`, "error");
    }
  };

  // --- Category assignment ---

  const handleCategoryChange = async (
    subscriptionId: number,
    categoryId: number | null,
  ) => {
    try {
      await assignCategory(subscriptionId, categoryId);
      await load();
    } catch (err) {
      addToast(
        err instanceof Error ? err.message : "Failed to assign category",
        "error",
      );
    }
  };

  // --- Bulk operations ---

  const toggleSelect = (id: number) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const handleBulkUnsubscribe = async () => {
    if (selected.size === 0 || !data) return;

    const usernames = data.channels
      .filter((ch) => selected.has(ch.id))
      .map((ch) => ch.username);

    const confirmed = await new Promise<boolean>((resolve) => {
      const wa = window.Telegram?.WebApp;
      if (wa?.showConfirm) {
        wa.showConfirm(
          `Unsubscribe from ${usernames.length} channel(s)?`,
          resolve,
        );
      } else {
        resolve(
          window.confirm(`Unsubscribe from ${usernames.length} channel(s)?`),
        );
      }
    });
    if (!confirmed) return;

    setSubmitting(true);
    try {
      await bulkUnsubscribe(usernames);
      addToast(`Unsubscribed from ${usernames.length} channel(s)`, "success");
      setSelected(new Set());
      await load();
    } catch (err) {
      addToast(
        err instanceof Error ? err.message : "Bulk unsubscribe failed",
        "error",
      );
    } finally {
      setSubmitting(false);
    }
  };

  const handleBulkCategory = async (categoryId: number | null) => {
    if (selected.size === 0) return;
    const ids = Array.from(selected);
    setSubmitting(true);
    try {
      await bulkAssignCategory(ids, categoryId);
      addToast("Category updated for selected channels", "success");
      setSelected(new Set());
      await load();
    } catch (err) {
      addToast(
        err instanceof Error ? err.message : "Bulk category failed",
        "error",
      );
    } finally {
      setSubmitting(false);
    }
  };

  // --- Grouping channels by category ---

  const groupByCategory = (
    channels: ChannelSubscription[],
  ): { category: Category | null; channels: ChannelSubscription[] }[] => {
    const catMap = new Map<number, Category>();
    for (const cat of categories) {
      catMap.set(cat.id, cat);
    }

    const groups = new Map<number | null, ChannelSubscription[]>();
    for (const ch of channels) {
      const key = ch.category_id ?? null;
      if (!groups.has(key)) {
        groups.set(key, []);
      }
      groups.get(key)!.push(ch);
    }

    const result: { category: Category | null; channels: ChannelSubscription[] }[] = [];

    // Named categories first
    for (const cat of categories) {
      const chans = groups.get(cat.id);
      if (chans && chans.length > 0) {
        result.push({ category: cat, channels: chans });
      }
    }

    // Uncategorized last
    const uncategorized = groups.get(null);
    if (uncategorized && uncategorized.length > 0) {
      result.push({ category: null, channels: uncategorized });
    }

    return result;
  };

  // --- Render helpers ---

  const truncate = (text: string, maxLen: number): string =>
    text.length <= maxLen ? text : text.slice(0, maxLen) + "...";

  const renderChannelItem = (ch: ChannelSubscription) => {
    const expanded = expandedChannels[ch.username];
    const isExpanded = !!expanded;

    return (
      <li key={ch.id} className="channel-item">
        <div className="channel-row">
          <input
            type="checkbox"
            checked={selected.has(ch.id)}
            onChange={() => toggleSelect(ch.id)}
            className="channel-checkbox"
          />
          <div
            className="channel-info"
            onClick={() => toggleChannelPosts(ch.username)}
            style={{ cursor: "pointer", flex: 1 }}
          >
            <span className="channel-name">
              @{ch.username}
              {ch.title ? ` - ${ch.title}` : ""}
            </span>
            {ch.fetch_error_count > 0 && (
              <span className="channel-errors">
                {ch.fetch_error_count} errors
              </span>
            )}
          </div>
          <select
            className="category-select"
            value={ch.category_id ?? ""}
            onChange={(e) => {
              const val = e.target.value;
              handleCategoryChange(ch.id, val ? Number(val) : null);
            }}
          >
            <option value="">No category</option>
            {categories.map((cat) => (
              <option key={cat.id} value={cat.id}>
                {cat.name}
              </option>
            ))}
          </select>
          <button
            className="btn-unsub"
            onClick={() => handleUnsubscribe(ch.username)}
            disabled={submitting}
          >
            Remove
          </button>
        </div>

        {isExpanded && (
          <div className="channel-posts">
            {expanded.loading ? (
              <div className="loading-posts">Loading posts...</div>
            ) : expanded.posts.length === 0 ? (
              <div className="no-posts">No recent posts</div>
            ) : (
              <ul className="posts-list">
                {expanded.posts.map((post) => (
                  <li key={post.id} className="post-item">
                    <span className="post-date">
                      {new Date(post.date).toLocaleDateString()}
                    </span>
                    <span className="post-text">
                      {truncate(post.text, 100)}
                    </span>
                    {post.topic_tag && (
                      <span className="post-tag">{post.topic_tag}</span>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </li>
    );
  };

  // --- Main render ---

  if (loading) return <div className="loading">Loading channels...</div>;
  if (error) return <div className="error">{error}</div>;
  if (!data) return null;

  const groups = groupByCategory(data.channels);

  return (
    <div className="channel-list">
      <form className="subscribe-form" onSubmit={handlePreview}>
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="@channel_name or t.me/channel"
          disabled={submitting || resolving}
        />
        <button
          type="submit"
          disabled={submitting || resolving || !input.trim()}
        >
          {resolving ? "..." : "Preview"}
        </button>
      </form>

      {preview && (
        <div className="channel-preview">
          <div className="preview-title">{preview.title}</div>
          {preview.description && (
            <div className="preview-description">{preview.description}</div>
          )}
          {preview.member_count != null && (
            <div className="preview-members">
              {preview.member_count.toLocaleString()} members
            </div>
          )}
          <div className="preview-actions">
            <button
              onClick={handleConfirmSubscribe}
              disabled={submitting}
              className="btn-confirm"
            >
              {submitting ? "..." : "Confirm Subscribe"}
            </button>
            <button onClick={handleCancelPreview} className="btn-cancel">
              Cancel
            </button>
          </div>
        </div>
      )}

      <div className="slot-info">
        {data.unlimited_channels || data.max_channels == null
          ? `${data.active_count} channels subscribed`
          : `${data.active_count}/${data.max_channels} slots used`}
      </div>

      {selected.size > 0 && (
        <div className="bulk-toolbar">
          <span className="bulk-count">{selected.size} selected</span>
          <button
            className="btn-bulk-unsub"
            onClick={handleBulkUnsubscribe}
            disabled={submitting}
          >
            Unsubscribe Selected
          </button>
          <select
            className="bulk-category-select"
            defaultValue=""
            onChange={(e) => {
              const val = e.target.value;
              if (val === "") return;
              handleBulkCategory(val === "none" ? null : Number(val));
            }}
          >
            <option value="" disabled>
              Set Category
            </option>
            <option value="none">No category</option>
            {categories.map((cat) => (
              <option key={cat.id} value={cat.id}>
                {cat.name}
              </option>
            ))}
          </select>
          <button
            className="btn-bulk-clear"
            onClick={() => setSelected(new Set())}
          >
            Clear
          </button>
        </div>
      )}

      {data.channels.length === 0 ? (
        <p className="empty">No subscriptions yet. Add a channel above.</p>
      ) : (
        groups.map((group) => (
          <div key={group.category?.id ?? "uncategorized"} className="channel-group">
            <div className="category-header">
              {group.category ? group.category.name : "Uncategorized"}
              <span className="category-count">
                ({group.channels.length})
              </span>
            </div>
            <ul className="channels">
              {group.channels.map(renderChannelItem)}
            </ul>
          </div>
        ))
      )}

      {data.active_count > 0 && (
        <button
          className="btn-trigger"
          onClick={handleTrigger}
          disabled={triggering}
        >
          {triggering ? "Generating..." : "Generate Digest Now"}
        </button>
      )}
    </div>
  );
}
