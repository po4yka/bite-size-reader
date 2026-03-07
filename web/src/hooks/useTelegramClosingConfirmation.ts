import { useEffect } from "react";
import { useAuth } from "../auth/AuthProvider";

export function useTelegramClosingConfirmation(isDirty: boolean): void {
  const { mode } = useAuth();

  useEffect(() => {
    const webApp = window.Telegram?.WebApp;
    if (mode !== "telegram-webapp" || !webApp) {
      return;
    }

    if (isDirty) {
      webApp.enableClosingConfirmation?.();
    } else {
      webApp.disableClosingConfirmation?.();
    }

    return () => {
      webApp.disableClosingConfirmation?.();
    };
  }, [isDirty, mode]);
}
