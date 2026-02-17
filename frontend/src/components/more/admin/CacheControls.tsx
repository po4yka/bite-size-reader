import { useState } from "react";
import { clearCache } from "../../../api/admin";
import { useToast } from "../../../hooks/useToast";

export default function CacheControls() {
  const { addToast } = useToast();
  const [clearing, setClearing] = useState(false);

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
    try {
      const result = await clearCache();
      addToast(`Cleared ${result.cleared_keys} cached key(s).`, "success");
    } catch (e) {
      addToast(e instanceof Error ? e.message : "Failed to clear cache", "error");
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
