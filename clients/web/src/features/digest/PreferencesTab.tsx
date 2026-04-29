import { useEffect, useState } from "react";
import {
  Button,
  InlineLoading,
  InlineNotification,
  NumberInput,
  Select,
  SelectItem,
  Tile,
  TimePicker,
} from "../../design";
import { useDigestPreferences, useUpdateDigestPreferences } from "../../hooks/useDigest";

export function PreferencesTab() {
  const preferencesQuery = useDigestPreferences();

  const [deliveryTime, setDeliveryTime] = useState("09:00");
  const [timezone, setTimezone] = useState("UTC");
  const [hoursLookback, setHoursLookback] = useState(24);
  const [maxPostsPerDigest, setMaxPostsPerDigest] = useState(20);
  const [minRelevanceScore, setMinRelevanceScore] = useState(0.3);

  useEffect(() => {
    if (!preferencesQuery.data) return;
    setDeliveryTime(preferencesQuery.data.deliveryTime);
    setTimezone(preferencesQuery.data.timezone);
    setHoursLookback(preferencesQuery.data.hoursLookback);
    setMaxPostsPerDigest(preferencesQuery.data.maxPostsPerDigest);
    setMinRelevanceScore(preferencesQuery.data.minRelevanceScore);
  }, [preferencesQuery.data]);

  const saveMutation = useUpdateDigestPreferences();

  const data = preferencesQuery.data;

  return (
    <div className="page-section">
      <Tile>
        <h3>Digest preferences</h3>

        {preferencesQuery.isLoading && <InlineLoading description="Loading preferences..." />}

        {(preferencesQuery.error || saveMutation.error) && (
          <InlineNotification
            kind="error"
            title="Digest preference operation failed"
            subtitle={
              (preferencesQuery.error || saveMutation.error) instanceof Error
                ? ((preferencesQuery.error || saveMutation.error) as Error).message
                : "Unknown error"
            }
            hideCloseButton
          />
        )}

        {data && (
          <div className="digest-form-grid">
            <TimePicker
              id="digest-delivery-time"
              labelText={`Delivery time (${data.deliveryTimeSource})`}
              value={deliveryTime}
              onChange={(event) => setDeliveryTime(event.currentTarget.value)}
            />

            <Select
              id="digest-timezone"
              labelText={`Timezone (${data.timezoneSource})`}
              value={timezone}
              onChange={(event) => setTimezone(event.currentTarget.value)}
            >
              <SelectItem text="UTC" value="UTC" />
              <SelectItem text="Europe/London" value="Europe/London" />
              <SelectItem text="Europe/Moscow" value="Europe/Moscow" />
              <SelectItem text="US/Eastern" value="US/Eastern" />
              <SelectItem text="US/Pacific" value="US/Pacific" />
              <SelectItem text="Asia/Tokyo" value="Asia/Tokyo" />
              <SelectItem text="Asia/Shanghai" value="Asia/Shanghai" />
            </Select>

            <NumberInput
              id="digest-hours-lookback"
              label={`Hours lookback (${data.hoursLookbackSource})`}
              min={1}
              max={168}
              value={hoursLookback}
              onChange={(_, state) => setHoursLookback(Number(state.value || hoursLookback))}
            />

            <NumberInput
              id="digest-max-posts"
              label={`Max posts per digest (${data.maxPostsPerDigestSource})`}
              min={1}
              max={100}
              value={maxPostsPerDigest}
              onChange={(_, state) => setMaxPostsPerDigest(Number(state.value || maxPostsPerDigest))}
            />

            <NumberInput
              id="digest-min-relevance"
              label={`Min relevance score (${data.minRelevanceScoreSource})`}
              min={0}
              max={1}
              step={0.05}
              value={minRelevanceScore}
              onChange={(_, state) => {
                const value = Number(state.value);
                if (Number.isFinite(value)) {
                  setMinRelevanceScore(Math.max(0, Math.min(1, value)));
                }
              }}
            />
          </div>
        )}

        <div className="form-actions">
          <Button disabled={saveMutation.isPending} onClick={() => saveMutation.mutate({ delivery_time: deliveryTime, timezone, hours_lookback: hoursLookback, max_posts_per_digest: maxPostsPerDigest, min_relevance_score: minRelevanceScore })}>
            Save Digest Preferences
          </Button>

          {saveMutation.isSuccess && (
            <InlineNotification
              kind="success"
              title="Preferences saved"
              subtitle="Digest settings were updated successfully."
              hideCloseButton
            />
          )}
        </div>
      </Tile>
    </div>
  );
}
