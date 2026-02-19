import { useCallback, useEffect, useState } from "react";
import {
  fetchChannels,
  subscribeChannel,
  unsubscribeChannel,
  triggerDigest,
  type ChannelsData,
} from "../api/digest";
import { useToast } from "../hooks/useToast";

export default function ChannelList() {
  const { addToast } = useToast();
  const [data, setData] = useState<ChannelsData | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [input, setInput] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [triggering, setTriggering] = useState(false);

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

  useEffect(() => {
    load();
  }, [load]);

  const handleSubscribe = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || submitting) return;
    setSubmitting(true);
    try {
      const result = await subscribeChannel(input.trim());
      addToast(`Subscribed to @${result.username}`, "success");
      setInput("");
      await load();
    } catch (err) {
      addToast(err instanceof Error ? err.message : "Subscribe failed", "error");
    } finally {
      setSubmitting(false);
    }
  };

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
      addToast(err instanceof Error ? err.message : "Unsubscribe failed", "error");
    } finally {
      setSubmitting(false);
    }
  };

  const handleTrigger = async () => {
    if (triggering) return;
    setTriggering(true);
    try {
      await triggerDigest();
      addToast("Digest queued! Check your Telegram chat.", "success");
    } catch (err) {
      addToast(err instanceof Error ? err.message : "Trigger failed", "error");
    } finally {
      setTriggering(false);
    }
  };

  if (loading) return <div className="loading">Loading channels...</div>;
  if (error) return <div className="error">{error}</div>;
  if (!data) return null;

  return (
    <div className="channel-list">
      <form className="subscribe-form" onSubmit={handleSubscribe}>
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="@channel_name or t.me/channel"
          disabled={submitting}
        />
        <button type="submit" disabled={submitting || !input.trim()}>
          {submitting ? "..." : "Subscribe"}
        </button>
      </form>

      <div className="slot-info">
        {data.unlimited_channels || data.max_channels == null
          ? `${data.active_count} channels subscribed`
          : `${data.active_count}/${data.max_channels} slots used`}
      </div>

      {data.channels.length === 0 ? (
        <p className="empty">No subscriptions yet. Add a channel above.</p>
      ) : (
        <ul className="channels">
          {data.channels.map((ch) => (
            <li key={ch.id} className="channel-item">
              <div className="channel-info">
                <span className="channel-name">@{ch.username}</span>
                {ch.fetch_error_count > 0 && (
                  <span className="channel-errors">
                    {ch.fetch_error_count} errors
                  </span>
                )}
              </div>
              <button
                className="btn-unsub"
                onClick={() => handleUnsubscribe(ch.username)}
                disabled={submitting}
              >
                Remove
              </button>
            </li>
          ))}
        </ul>
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
