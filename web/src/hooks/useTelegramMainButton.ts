import { useEffect } from "react";
import { useAuth } from "../auth/AuthProvider";

interface TelegramMainButtonOptions {
  visible: boolean;
  text: string;
  disabled?: boolean;
  loading?: boolean;
  onClick: () => void;
}

export function useTelegramMainButton(options: TelegramMainButtonOptions): void {
  const { mode } = useAuth();

  useEffect(() => {
    const webApp = window.Telegram?.WebApp;
    const mainButton = webApp?.MainButton;

    if (mode !== "telegram-webapp" || !mainButton) {
      return;
    }

    if (!options.visible) {
      mainButton.hideProgress?.();
      mainButton.hide?.();
      return;
    }

    mainButton.setText?.(options.text);
    if (options.disabled) {
      mainButton.disable?.();
    } else {
      mainButton.enable?.();
    }

    if (options.loading) {
      mainButton.showProgress?.(true);
    } else {
      mainButton.hideProgress?.();
    }

    mainButton.show?.();
    mainButton.onClick?.(options.onClick);

    return () => {
      mainButton.offClick?.(options.onClick);
      mainButton.hideProgress?.();
    };
  }, [mode, options.disabled, options.loading, options.onClick, options.text, options.visible]);
}
