import { useState } from "react";
import { clearCache } from "../../../api/admin";

export default function CacheControls() {
  const [clearing, setClearing] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const handleClear = async () => {
    if (clearing) return;

    const confirmed = await new Promise<boolean>((resolve) => {
      const wa = window.Telegram?.WebApp;
      if (wa?.showConfirm) {
        wa.showConfirm("Clear the entire URL cache?", resolve);
      } else {
        resolve(window.confirm("Clear the entire URL cache?"));
      }
    });
    if (!confirmed) return;

    window.Telegram?.WebApp?.HapticFeedback?.impactOccurred("medium");
    setClearing(true);
    setMessage("");
    setError("");
    try {
      const result = await clearCache();
      setMessage(`Cleared ${result.cleared_keys} cached key(s).`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to clear cache");
    } finally {
      setClearing(false);
    }
  };

  return (
    <div className="admin-section">
      <h3 className="admin-section-title">Cache</h3>

      <p className="admin-section-desc">
        Clear the Redis URL cache. This forces fresh content extraction on next
        request.
      </p>

      {message && <div className="message">{message}</div>}
      {error && <div className="error">{error}</div>}

      <button
        className="btn-admin"
        onClick={handleClear}
        disabled={clearing}
      >
        {clearing ? "Clearing..." : "Clear URL Cache"}
      </button>
    </div>
  );
}
