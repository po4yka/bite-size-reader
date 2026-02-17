import { useState } from "react";
import { triggerChannelDigest } from "../../../api/admin";

export default function ChannelDigest() {
  const [input, setInput] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || submitting) return;
    setSubmitting(true);
    setMessage("");
    setError("");
    try {
      const result = await triggerChannelDigest(input.trim());
      setMessage(
        `Digest ${result.status} for @${result.channel}. Check Telegram.`,
      );
      setInput("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Trigger failed");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="admin-section">
      <h3 className="admin-section-title">Channel Digest</h3>

      <p className="admin-section-desc">
        Trigger a digest for a single channel. The result will be delivered to
        your Telegram chat.
      </p>

      {message && <div className="message">{message}</div>}
      {error && <div className="error">{error}</div>}

      <form className="admin-form" onSubmit={handleSubmit}>
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="@channel_name"
          disabled={submitting}
        />
        <button type="submit" disabled={submitting || !input.trim()}>
          {submitting ? "Triggering..." : "Trigger Digest"}
        </button>
      </form>
    </div>
  );
}
