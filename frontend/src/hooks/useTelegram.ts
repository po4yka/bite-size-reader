import { useCallback, useEffect, useMemo, useState } from "react";

export function useTelegram() {
  const [webApp, setWebApp] = useState<TelegramWebApp | null>(null);

  useEffect(() => {
    const tg = window.Telegram?.WebApp;
    if (tg) {
      tg.ready();
      tg.expand();
      setWebApp(tg);
    }
  }, []);

  const haptic = useMemo(() => {
    const hf = webApp?.HapticFeedback;
    return {
      impact: (style: "light" | "medium" | "heavy" | "rigid" | "soft") => hf?.impactOccurred(style),
      notification: (type: "error" | "success" | "warning") => hf?.notificationOccurred(type),
      selection: () => hf?.selectionChanged(),
    };
  }, [webApp]);

  const showConfirm = useCallback(
    (message: string): Promise<boolean> =>
      new Promise((resolve) => {
        if (webApp?.showConfirm) {
          webApp.showConfirm(message, resolve);
        } else {
          resolve(window.confirm(message));
        }
      }),
    [webApp],
  );

  const showAlert = useCallback(
    (message: string): Promise<void> =>
      new Promise((resolve) => {
        if (webApp?.showAlert) {
          webApp.showAlert(message, resolve);
        } else {
          window.alert(message);
          resolve();
        }
      }),
    [webApp],
  );

  return {
    webApp,
    initData: webApp?.initData ?? "",
    user: webApp?.initDataUnsafe?.user ?? null,
    haptic,
    showConfirm,
    showAlert,
  };
}
