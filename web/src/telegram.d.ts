interface TelegramWebApp {
  initData: string;
  colorScheme?: "light" | "dark";
  themeParams?: Record<string, string>;
  viewportHeight?: number;
  viewportStableHeight?: number;
  ready?: () => void;
  expand?: () => void;
  onEvent?: (eventType: string, handler: () => void) => void;
  offEvent?: (eventType: string, handler: () => void) => void;
}

interface TelegramWindow {
  WebApp?: TelegramWebApp;
}

interface Window {
  Telegram?: TelegramWindow;
  onTelegramAuth?: (user: {
    id: number;
    first_name?: string;
    last_name?: string;
    username?: string;
    photo_url?: string;
    auth_date: number;
    hash: string;
  }) => void;
}
