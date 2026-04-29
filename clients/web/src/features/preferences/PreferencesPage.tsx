import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Button,
  InlineNotification,
  NumberInput,
  Select,
  SelectItem,
  SkeletonText,
  Tile,
  TimePicker,
} from "../../design";
import { useUserPreferences, useUserStats, useUpdateUserPreferences } from "../../hooks/useUser";
import { QueryErrorNotification } from "../../components/QueryErrorNotification";
import { useTelegramClosingConfirmation } from "../../hooks/useTelegramClosingConfirmation";
import { useTelegramMainButton } from "../../hooks/useTelegramMainButton";
import ReadingStreakSection from "./ReadingStreakSection";
import ReadingGoalsSection from "./ReadingGoalsSection";
import TelegramLinkSection from "./TelegramLinkSection";
import SessionsSection from "./SessionsSection";
import AccountSection from "./AccountSection";

function parseDeliveryTime(settings: Record<string, unknown> | null): string {
  const raw = settings?.delivery_time;
  return typeof raw === "string" ? raw : "09:00";
}

export default function PreferencesPage() {
  const preferencesQuery = useUserPreferences();
  const statsQuery = useUserStats();

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

  const saveMutation = useUpdateUserPreferences(() => {
    void preferencesQuery.refetch();
  });

  const initialLangPreference = useMemo(
    () => (preferencesQuery.data?.langPreference ?? "auto") as "auto" | "en" | "ru",
    [preferencesQuery.data?.langPreference],
  );
  const initialDeliveryTime = useMemo(
    () => parseDeliveryTime(preferencesQuery.data?.appSettings ?? null),
    [preferencesQuery.data?.appSettings],
  );
  const initialDailyTarget = useMemo(() => {
    const value = preferencesQuery.data?.appSettings?.daily_target;
    return typeof value === "number" ? value : 5;
  }, [preferencesQuery.data?.appSettings]);

  const isDirty = Boolean(
    preferencesQuery.data &&
      (langPreference !== initialLangPreference ||
        deliveryTime !== initialDeliveryTime ||
        dailyTarget !== initialDailyTarget),
  );
  const isInitialLoading =
    (preferencesQuery.isLoading && !preferencesQuery.data) || (statsQuery.isLoading && !statsQuery.data);

  useTelegramClosingConfirmation(isDirty || saveMutation.isPending);

  const handleSave = useCallback(() => {
    if (!isDirty || saveMutation.isPending) return;
    saveMutation.mutate({
      lang_preference: langPreference,
      app_settings: {
        delivery_time: deliveryTime,
        daily_target: dailyTarget,
      },
    });
  }, [isDirty, saveMutation, langPreference, deliveryTime, dailyTarget]);

  useTelegramMainButton({
    visible: Boolean(preferencesQuery.data),
    text: "Save Preferences",
    disabled: !isDirty || saveMutation.isPending,
    loading: saveMutation.isPending,
    onClick: handleSave,
  });

  return (
    <section className="page-section">
      <h1>Preferences</h1>

      {isInitialLoading && (
        <>
          <Tile>
            <SkeletonText heading width="30%" />
            <SkeletonText paragraph lineCount={3} />
            <SkeletonText paragraph lineCount={5} />
          </Tile>
          <Tile>
            <SkeletonText heading width="28%" />
            <SkeletonText paragraph lineCount={5} />
          </Tile>
        </>
      )}

      <QueryErrorNotification error={preferencesQuery.error ?? statsQuery.error} title="Failed to load preferences" />

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

          <Button onClick={handleSave} disabled={!isDirty || saveMutation.isPending}>
            Save preferences
          </Button>

          <QueryErrorNotification error={saveMutation.error} title="Save failed" />

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

      <ReadingStreakSection />
      <ReadingGoalsSection />
      <TelegramLinkSection />
      <SessionsSection />
      <AccountSection />
    </section>
  );
}
