import { useState } from "react";
import { triggerChannelDigest } from "../../../api/admin";
import { useToast } from "../../../hooks/useToast";

export default function ChannelDigest() {
  const { addToast } = useToast();
  const [input, setInput] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || submitting) return;
    setSubmitting(true);
    try {
      const result = await triggerChannelDigest(input.trim());
      addToast(`Digest ${result.status} for @${result.channel}. Check Telegram.`, "success");
      setInput("");
    } catch (err) {
      addToast(err instanceof Error ? err.message : "Trigger failed", "error");
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
