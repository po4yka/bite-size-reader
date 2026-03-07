interface TelegramBackButton {
  show?: () => void;
  hide?: () => void;
  onClick?: (handler: () => void) => void;
  offClick?: (handler: () => void) => void;
}

interface TelegramMainButton {
  show?: () => void;
  hide?: () => void;
  enable?: () => void;
  disable?: () => void;
  setText?: (text: string) => void;
  showProgress?: (leaveActive?: boolean) => void;
  hideProgress?: () => void;
  onClick?: (handler: () => void) => void;
  offClick?: (handler: () => void) => void;
  setParams?: (params: {
    text?: string;
    is_active?: boolean;
    is_visible?: boolean;
    is_progress_visible?: boolean;
    color?: string;
    text_color?: string;
  }) => void;
}

interface TelegramWebApp {
  initData: string;
  colorScheme?: "light" | "dark";
  themeParams?: Record<string, string>;
  viewportHeight?: number;
  viewportStableHeight?: number;
  BackButton?: TelegramBackButton;
  MainButton?: TelegramMainButton;
  ready?: () => void;
  expand?: () => void;
  enableClosingConfirmation?: () => void;
  disableClosingConfirmation?: () => void;
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
