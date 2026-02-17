/// <reference types="vite/client" />

interface TelegramWebAppUser {
  id: number;
  first_name: string;
  last_name?: string;
  username?: string;
}

interface TelegramBackButton {
  show: () => void;
  hide: () => void;
  onClick: (cb: () => void) => void;
  offClick: (cb: () => void) => void;
  isVisible: boolean;
}

interface TelegramMainButton {
  text: string;
  setText: (text: string) => TelegramMainButton;
  show: () => TelegramMainButton;
  hide: () => TelegramMainButton;
  enable: () => TelegramMainButton;
  disable: () => TelegramMainButton;
  showProgress: (leaveActive?: boolean) => TelegramMainButton;
  hideProgress: () => TelegramMainButton;
  onClick: (cb: () => void) => TelegramMainButton;
  offClick: (cb: () => void) => TelegramMainButton;
  isVisible: boolean;
  isActive: boolean;
  isProgressVisible: boolean;
  color: string;
  textColor: string;
  setParams: (params: {
    text?: string;
    color?: string;
    text_color?: string;
    is_active?: boolean;
    is_visible?: boolean;
  }) => TelegramMainButton;
}

interface TelegramSecondaryButton {
  text: string;
  setText: (text: string) => TelegramSecondaryButton;
  show: () => TelegramSecondaryButton;
  hide: () => TelegramSecondaryButton;
  enable: () => TelegramSecondaryButton;
  disable: () => TelegramSecondaryButton;
  showProgress: (leaveActive?: boolean) => TelegramSecondaryButton;
  hideProgress: () => TelegramSecondaryButton;
  onClick: (cb: () => void) => TelegramSecondaryButton;
  offClick: (cb: () => void) => TelegramSecondaryButton;
  isVisible: boolean;
  isActive: boolean;
  isProgressVisible: boolean;
  color: string;
  textColor: string;
  setParams: (params: {
    text?: string;
    color?: string;
    text_color?: string;
    is_active?: boolean;
    is_visible?: boolean;
  }) => TelegramSecondaryButton;
}

interface TelegramSettingsButton {
  show: () => void;
  hide: () => void;
  onClick: (cb: () => void) => void;
  offClick: (cb: () => void) => void;
  isVisible: boolean;
}

interface TelegramHapticFeedback {
  impactOccurred: (style: "light" | "medium" | "heavy" | "rigid" | "soft") => void;
  notificationOccurred: (type: "error" | "success" | "warning") => void;
  selectionChanged: () => void;
}

interface TelegramCloudStorage {
  setItem: (key: string, value: string, callback?: (error: string | null, result?: boolean) => void) => void;
  getItem: (key: string, callback: (error: string | null, value?: string) => void) => void;
  getItems: (keys: string[], callback: (error: string | null, values?: Record<string, string>) => void) => void;
  removeItem: (key: string, callback?: (error: string | null, result?: boolean) => void) => void;
  removeItems: (keys: string[], callback?: (error: string | null, result?: boolean) => void) => void;
  getKeys: (callback: (error: string | null, keys?: string[]) => void) => void;
}

interface TelegramSafeAreaInset {
  top: number;
  bottom: number;
  left: number;
  right: number;
}

interface TelegramContentSafeAreaInset {
  top: number;
  bottom: number;
  left: number;
  right: number;
}

interface PopupButton {
  id?: string;
  type?: "default" | "ok" | "close" | "cancel" | "destructive";
  text?: string;
}

interface PopupParams {
  title?: string;
  message: string;
  buttons?: PopupButton[];
}

interface TelegramWebApp {
  initData: string;
  initDataUnsafe: {
    user?: TelegramWebAppUser;
  };
  version: string;
  platform: string;
  colorScheme: "light" | "dark";
  isFullscreen: boolean;
  safeAreaInset: TelegramSafeAreaInset;
  contentSafeAreaInset: TelegramContentSafeAreaInset;
  themeParams: Record<string, string>;

  // Lifecycle
  ready: () => void;
  expand: () => void;
  close: () => void;
  isVersionAtLeast: (version: string) => boolean;

  // UI
  MainButton: TelegramMainButton;
  SecondaryButton: TelegramSecondaryButton;
  BackButton: TelegramBackButton;
  SettingsButton: TelegramSettingsButton;
  HapticFeedback: TelegramHapticFeedback;
  CloudStorage: TelegramCloudStorage;

  // Header / Background
  setHeaderColor: (color: "bg_color" | "secondary_bg_color" | string) => void;
  setBackgroundColor: (color: "bg_color" | "secondary_bg_color" | string) => void;
  setBottomBarColor: (color: "bg_color" | "secondary_bg_color" | "bottom_bar_bg_color" | string) => void;

  // Popups
  showPopup: (params: PopupParams, callback?: (buttonId: string) => void) => void;
  showAlert: (message: string, callback?: () => void) => void;
  showConfirm: (message: string, callback: (confirmed: boolean) => void) => void;

  // Fullscreen
  requestFullscreen: () => void;
  exitFullscreen: () => void;

  // Swipe / Close behavior
  disableVerticalSwipes: () => void;
  enableVerticalSwipes: () => void;
  enableClosingConfirmation: () => void;
  disableClosingConfirmation: () => void;
  isClosingConfirmationEnabled: boolean;

  // Keyboard
  hideKeyboard: () => void;
}

interface Window {
  Telegram?: {
    WebApp: TelegramWebApp;
  };
}
