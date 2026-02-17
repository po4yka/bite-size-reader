import { useCallback, useEffect, useState } from "react";
import {
  fetchPreferences,
  updatePreferences,
  type DigestPreferences,
} from "../api/digest";

export default function PreferencesForm() {
  const [prefs, setPrefs] = useState<DigestPreferences | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");

  // Form state
  const [deliveryTime, setDeliveryTime] = useState("");
  const [timezone, setTimezone] = useState("");
  const [hoursLookback, setHoursLookback] = useState(24);
  const [maxPosts, setMaxPosts] = useState(20);
  const [minRelevance, setMinRelevance] = useState(0.3);

  const load = useCallback(async () => {
    try {
      setError("");
      const result = await fetchPreferences();
      setPrefs(result);
      setDeliveryTime(result.delivery_time);
      setTimezone(result.timezone);
      setHoursLookback(result.hours_lookback);
      setMaxPosts(result.max_posts_per_digest);
      setMinRelevance(result.min_relevance_score);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load preferences");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    if (saving) return;
    setSaving(true);
    setMessage("");
    try {
      const updated = await updatePreferences({
        delivery_time: deliveryTime,
        timezone,
        hours_lookback: hoursLookback,
        max_posts_per_digest: maxPosts,
        min_relevance_score: minRelevance,
      });
      setPrefs(updated);
      setMessage("Preferences saved");
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <div className="loading">Loading preferences...</div>;
  if (error) return <div className="error">{error}</div>;
  if (!prefs) return null;

  return (
    <form className="preferences-form" onSubmit={handleSave}>
      {message && <div className="message">{message}</div>}

      <label className="field">
        <span className="field-label">
          Delivery Time
          <span className="source-badge">{prefs.delivery_time_source}</span>
        </span>
        <input
          type="time"
          value={deliveryTime}
          onChange={(e) => setDeliveryTime(e.target.value)}
        />
      </label>

      <label className="field">
        <span className="field-label">
          Timezone
          <span className="source-badge">{prefs.timezone_source}</span>
        </span>
        <select value={timezone} onChange={(e) => setTimezone(e.target.value)}>
          <option value="UTC">UTC</option>
          <option value="Europe/Moscow">Europe/Moscow</option>
          <option value="Europe/London">Europe/London</option>
          <option value="US/Eastern">US/Eastern</option>
          <option value="US/Pacific">US/Pacific</option>
          <option value="Asia/Tokyo">Asia/Tokyo</option>
          <option value="Asia/Shanghai">Asia/Shanghai</option>
        </select>
      </label>

      <label className="field">
        <span className="field-label">
          Lookback Hours
          <span className="source-badge">{prefs.hours_lookback_source}</span>
        </span>
        <div className="range-row">
          <input
            type="range"
            min={1}
            max={168}
            value={hoursLookback}
            onChange={(e) => setHoursLookback(Number(e.target.value))}
          />
          <span className="range-value">{hoursLookback}h</span>
        </div>
      </label>

      <label className="field">
        <span className="field-label">
          Max Posts
          <span className="source-badge">{prefs.max_posts_per_digest_source}</span>
        </span>
        <div className="range-row">
          <input
            type="range"
            min={1}
            max={100}
            value={maxPosts}
            onChange={(e) => setMaxPosts(Number(e.target.value))}
          />
          <span className="range-value">{maxPosts}</span>
        </div>
      </label>

      <label className="field">
        <span className="field-label">
          Min Relevance
          <span className="source-badge">{prefs.min_relevance_score_source}</span>
        </span>
        <div className="range-row">
          <input
            type="range"
            min={0}
            max={1}
            step={0.05}
            value={minRelevance}
            onChange={(e) => setMinRelevance(Number(e.target.value))}
          />
          <span className="range-value">{minRelevance.toFixed(2)}</span>
        </div>
      </label>

      <button type="submit" className="btn-save" disabled={saving}>
        {saving ? "Saving..." : "Save Preferences"}
      </button>
    </form>
  );
}
