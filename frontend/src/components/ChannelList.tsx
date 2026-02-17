import { useCallback, useEffect, useState } from "react";
import {
  fetchChannels,
  subscribeChannel,
  unsubscribeChannel,
  triggerDigest,
  type ChannelsData,
} from "../api/digest";

export default function ChannelList() {
  const [data, setData] = useState<ChannelsData | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [input, setInput] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [triggering, setTriggering] = useState(false);
  const [message, setMessage] = useState("");

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
    setMessage("");
    try {
      const result = await subscribeChannel(input.trim());
      setMessage(`Subscribed to @${result.username}`);
      setInput("");
      await load();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Subscribe failed");
    } finally {
      setSubmitting(false);
    }
  };

  const handleUnsubscribe = async (username: string) => {
    if (submitting) return;
    setSubmitting(true);
    setMessage("");
    try {
      await unsubscribeChannel(username);
      setMessage(`Unsubscribed from @${username}`);
      await load();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Unsubscribe failed");
    } finally {
      setSubmitting(false);
    }
  };

  const handleTrigger = async () => {
    if (triggering) return;
    setTriggering(true);
    setMessage("");
    try {
      await triggerDigest();
      setMessage("Digest queued! Check your Telegram chat.");
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Trigger failed");
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
        {data.active_count}/{data.max_channels} slots used
      </div>

      {message && <div className="message">{message}</div>}

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
