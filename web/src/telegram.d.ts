interface TelegramWebApp {
  initData: string;
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
