import { useEffect, useRef, useState } from "react";
import { Button, InlineLoading, InlineNotification, Tile } from "@carbon/react";
import type { TelegramAuthPayload } from "./types";
import { useAuth } from "./AuthProvider";

function mapTelegramUserToPayload(user: {
  id: number;
  hash: string;
  auth_date: number;
  username?: string;
  first_name?: string;
  last_name?: string;
  photo_url?: string;
}): TelegramAuthPayload {
  return {
    id: user.id,
    hash: user.hash,
    auth_date: user.auth_date,
    username: user.username,
    first_name: user.first_name,
    last_name: user.last_name,
    photo_url: user.photo_url,
  };
}

export default function LoginPage() {
  const { login, logout, error, dismissError } = useAuth();
  const widgetRef = useRef<HTMLDivElement | null>(null);
  const [loading, setLoading] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);

  const botUsername = import.meta.env.VITE_TELEGRAM_BOT_USERNAME;

  useEffect(() => {
    const widgetNode = widgetRef.current;
    if (!widgetNode || !botUsername) {
      return;
    }

    window.onTelegramAuth = async (user) => {
      try {
        setLoading(true);
        setLocalError(null);
        dismissError();
        await login(mapTelegramUserToPayload(user));
      } catch (err) {
        setLocalError(err instanceof Error ? err.message : "Telegram sign-in failed.");
      } finally {
        setLoading(false);
      }
    };

    widgetNode.innerHTML = "";
    const script = document.createElement("script");
    script.src = "https://telegram.org/js/telegram-widget.js?22";
    script.async = true;
    script.setAttribute("data-telegram-login", botUsername);
    script.setAttribute("data-size", "large");
    script.setAttribute("data-userpic", "false");
    script.setAttribute("data-request-access", "write");
    script.setAttribute("data-onauth", "onTelegramAuth(user)");
    script.setAttribute("data-radius", "4");

    widgetNode.appendChild(script);

    return () => {
      delete window.onTelegramAuth;
      widgetNode.innerHTML = "";
    };
  }, [botUsername, dismissError, login]);

  return (
    <div className="login-page">
      <Tile className="login-card">
        <h2>Sign in to Bite-Size Reader</h2>
        <p>Use Telegram to authenticate and access your summaries.</p>

        {!botUsername && (
          <InlineNotification
            kind="error"
            title="Missing configuration"
            subtitle="Set VITE_TELEGRAM_BOT_USERNAME to enable Telegram Login Widget."
            hideCloseButton
          />
        )}

        {(error || localError) && (
          <InlineNotification
            kind="error"
            title="Authentication failed"
            subtitle={localError ?? error ?? "Unknown error"}
            hideCloseButton
          />
        )}

        {loading ? <InlineLoading description="Verifying Telegram credentials..." /> : <div ref={widgetRef} />}

        <InlineNotification
          kind="info"
          title="Security note"
          subtitle="Never share Telegram login confirmation codes. This app only uses Telegram widget auth."
          hideCloseButton
        />

        <div className="form-actions">
          <Button kind="ghost" onClick={logout}>
            Clear local session
          </Button>
          <Button kind="ghost" href="https://core.telegram.org/widgets/login" target="_blank" rel="noreferrer">
            About Telegram Login
          </Button>
        </div>
      </Tile>
    </div>
  );
}
