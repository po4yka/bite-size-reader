import { useEffect, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  Button,
  InlineLoading,
  InlineNotification,
  NumberInput,
  Select,
  SelectItem,
  Tile,
  TimePicker,
} from "@carbon/react";
import { fetchUserPreferences, fetchUserStats, updateUserPreferences } from "../../api/user";

function parseDeliveryTime(settings: Record<string, unknown> | null): string {
  const raw = settings?.delivery_time;
  return typeof raw === "string" ? raw : "09:00";
}

export default function PreferencesPage() {
  const preferencesQuery = useQuery({
    queryKey: ["user-preferences"],
    queryFn: () => fetchUserPreferences(),
  });

  const statsQuery = useQuery({
    queryKey: ["user-stats"],
    queryFn: () => fetchUserStats(),
  });

  const [langPreference, setLangPreference] = useState<"auto" | "en" | "ru">("auto");
  const [deliveryTime, setDeliveryTime] = useState("09:00");
  const [dailyTarget, setDailyTarget] = useState(5);

  useEffect(() => {
    if (!preferencesQuery.data) return;
    setLangPreference((preferencesQuery.data.langPreference ?? "auto") as "auto" | "en" | "ru");
    setDeliveryTime(parseDeliveryTime(preferencesQuery.data.appSettings));

    const target = preferencesQuery.data.appSettings?.daily_target;
    if (typeof target === "number") {
      setDailyTarget(target);
    }
  }, [preferencesQuery.data]);

  const saveMutation = useMutation({
    mutationFn: () =>
      updateUserPreferences({
        lang_preference: langPreference,
        app_settings: {
          delivery_time: deliveryTime,
          daily_target: dailyTarget,
        },
      }),
    onSuccess: () => {
      void preferencesQuery.refetch();
    },
  });

  return (
    <section className="page-section">
      <h1>Preferences</h1>

      {(preferencesQuery.isLoading || statsQuery.isLoading) && <InlineLoading description="Loading preferences…" />}

      {(preferencesQuery.error || statsQuery.error) && (
        <InlineNotification
          kind="error"
          title="Failed to load preferences"
          subtitle={(preferencesQuery.error ?? statsQuery.error) instanceof Error ? ((preferencesQuery.error ?? statsQuery.error) as Error).message : "Unknown error"}
          hideCloseButton
        />
      )}

      {preferencesQuery.data && (
        <Tile>
          <h3>Profile</h3>
          <p>User: @{preferencesQuery.data.telegramUsername ?? "unknown"}</p>

          <Select
            id="lang-preference"
            labelText="Preferred language"
            value={langPreference}
            onChange={(event) => setLangPreference(event.currentTarget.value as "auto" | "en" | "ru")}
          >
            <SelectItem value="auto" text="Auto" />
            <SelectItem value="en" text="English" />
            <SelectItem value="ru" text="Russian" />
          </Select>

          <TimePicker
            id="delivery-time"
            labelText="Digest delivery time"
            value={deliveryTime}
            onChange={(event) => setDeliveryTime(event.currentTarget.value)}
          />

          <NumberInput
            id="daily-target"
            label="Daily reading target"
            min={1}
            max={50}
            value={dailyTarget}
            onChange={(_, { value }) => setDailyTarget(Number(value))}
          />

          <Button onClick={() => saveMutation.mutate()} disabled={saveMutation.isPending}>
            Save preferences
          </Button>

          {saveMutation.error && (
            <InlineNotification
              kind="error"
              title="Save failed"
              subtitle={saveMutation.error instanceof Error ? saveMutation.error.message : "Unknown error"}
              hideCloseButton
            />
          )}

          {saveMutation.isSuccess && (
            <InlineNotification
              kind="success"
              title="Saved"
              subtitle="Preferences have been updated."
              hideCloseButton
            />
          )}
        </Tile>
      )}

      {statsQuery.data && (
        <Tile>
          <h3>Reading stats</h3>
          <ul>
            <li>Total summaries: {statsQuery.data.totalSummaries}</li>
            <li>Unread: {statsQuery.data.unreadCount}</li>
            <li>Read: {statsQuery.data.readCount}</li>
            <li>Total reading time: {statsQuery.data.totalReadingTimeMin} minutes</li>
            <li>Average reading time: {statsQuery.data.averageReadingTimeMin} minutes</li>
          </ul>
        </Tile>
      )}
    </section>
  );
}
