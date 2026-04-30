import { useCallback, useEffect, useMemo, useState } from "react";
import {
  BracketButton,
  BrutalistCard,
  BrutalistSkeletonText,
  MonoSelect,
  MonoSelectItem,
  NumberInput,
  StatusBadge,
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
    <section
      className="page-section preferences-page"
      style={{
        maxWidth: "var(--frost-strip-5, 880px)",
        padding: "var(--frost-pad-page, 32px)",
        display: "flex",
        flexDirection: "column",
        gap: "var(--frost-gap-section, 48px)",
      }}
    >
      <h1>Preferences</h1>

      {isInitialLoading && (
        <>
          <BrutalistCard>
            <BrutalistSkeletonText heading width="30%" />
            <BrutalistSkeletonText paragraph lineCount={3} />
            <BrutalistSkeletonText paragraph lineCount={5} />
          </BrutalistCard>
          <BrutalistCard>
            <BrutalistSkeletonText heading width="28%" />
            <BrutalistSkeletonText paragraph lineCount={5} />
          </BrutalistCard>
        </>
      )}

      <QueryErrorNotification error={preferencesQuery.error ?? statsQuery.error} title="Failed to load preferences" />

      {preferencesQuery.data && (
        <BrutalistCard>
          <p
            style={{
              fontFamily: "var(--frost-font-mono)",
              fontSize: "11px",
              fontWeight: 800,
              textTransform: "uppercase",
              letterSpacing: "1px",
              color: "color-mix(in oklch, var(--frost-ink) 55%, transparent)",
              marginBottom: "1rem",
            }}
          >
            § Profile
          </p>
          <p>User: @{preferencesQuery.data.telegramUsername ?? "unknown"}</p>

          <MonoSelect
            id="lang-preference"
            labelText="Preferred language"
            value={langPreference}
            onChange={(event) => setLangPreference(event.currentTarget.value as "auto" | "en" | "ru")}
          >
            <MonoSelectItem value="auto" text="Auto" />
            <MonoSelectItem value="en" text="English" />
            <MonoSelectItem value="ru" text="Russian" />
          </MonoSelect>

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

          <BracketButton onClick={handleSave} disabled={!isDirty || saveMutation.isPending}>
            Save preferences
          </BracketButton>

          <QueryErrorNotification error={saveMutation.error} title="Save failed" />

          {saveMutation.isSuccess && (
            <StatusBadge severity="info" title="Saved ✓">
              Preferences have been updated.
            </StatusBadge>
          )}
        </BrutalistCard>
      )}

      {statsQuery.data && (
        <BrutalistCard>
          <p
            style={{
              fontFamily: "var(--frost-font-mono)",
              fontSize: "11px",
              fontWeight: 800,
              textTransform: "uppercase",
              letterSpacing: "1px",
              color: "color-mix(in oklch, var(--frost-ink) 55%, transparent)",
              marginBottom: "1rem",
            }}
          >
            § Reading stats
          </p>
          <ul>
            <li>Total summaries: {statsQuery.data.totalSummaries}</li>
            <li>Unread: {statsQuery.data.unreadCount}</li>
            <li>Read: {statsQuery.data.readCount}</li>
            <li>Total reading time: {statsQuery.data.totalReadingTimeMin} minutes</li>
            <li>Average reading time: {statsQuery.data.averageReadingTimeMin} minutes</li>
          </ul>
        </BrutalistCard>
      )}

      <ReadingStreakSection />
      <ReadingGoalsSection />
      <TelegramLinkSection />
      <SessionsSection />
      <AccountSection />
    </section>
  );
}
