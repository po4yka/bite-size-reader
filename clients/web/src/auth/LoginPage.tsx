import { useCallback, useEffect, useRef, useState } from "react";
import {
  Accordion,
  AccordionItem,
  BracketButton,
  BrutalistCard,
  SparkLoading,
  StatusBadge,
} from "../design";
import SecretLoginForm from "../features/auth/SecretLoginForm";
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
  const [widgetReady, setWidgetReady] = useState(false);

  const botUsername = import.meta.env.VITE_TELEGRAM_BOT_USERNAME;

  const clearErrors = useCallback(() => {
    setLocalError(null);
    dismissError();
  }, [dismissError]);

  // Auto-dismiss local errors after 8 seconds
  useEffect(() => {
    if (!localError) return;
    const timer = setTimeout(() => setLocalError(null), 8_000);
    return () => clearTimeout(timer);
  }, [localError]);

  // Load Telegram widget
  useEffect(() => {
    const widgetNode = widgetRef.current;
    if (!widgetNode || !botUsername) return;

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
    setWidgetReady(false);

    const script = document.createElement("script");
    script.src = "https://telegram.org/js/telegram-widget.js?22";
    script.async = true;
    script.setAttribute("data-telegram-login", botUsername);
    script.setAttribute("data-size", "large");
    script.setAttribute("data-userpic", "false");
    script.setAttribute("data-request-access", "write");
    script.setAttribute("data-onauth", "onTelegramAuth(user)");
    script.setAttribute("data-radius", "4");

    // Detect when widget iframe is inserted
    const observer = new MutationObserver(() => {
      if (widgetNode.querySelector("iframe")) {
        setWidgetReady(true);
        observer.disconnect();
      }
    });
    observer.observe(widgetNode, { childList: true, subtree: true });

    widgetNode.appendChild(script);

    return () => {
      observer.disconnect();
      delete window.onTelegramAuth;
      widgetNode.innerHTML = "";
    };
  }, [botUsername, dismissError, login]);

  const displayError = localError ?? error;

  return (
    <div
      className="login-page"
      style={{
        display: "flex",
        justifyContent: "center",
        alignItems: "center",
        minHeight: "100vh",
        padding: "var(--frost-pad-page, 32px)",
      }}
    >
      <BrutalistCard
        className="login-card"
        style={{ maxWidth: "var(--frost-strip-3, 528px)", width: "100%" }}
      >
        <div className="login-header" style={{ marginBottom: "1.5rem" }}>
          <h2
            style={{
              fontFamily: "var(--frost-font-mono)",
              fontSize: "13px",
              fontWeight: 800,
              textTransform: "uppercase",
              letterSpacing: "2px",
            }}
          >
            Ratatoskr
          </h2>
          <p
            className="page-subtitle"
            style={{ color: "color-mix(in oklch, var(--frost-ink) 55%, transparent)", marginTop: "0.5rem" }}
          >
            Sign in to access your summaries.
          </p>
        </div>

        <div className="login-hero" style={{ marginBottom: "1rem" }}>
          {!botUsername && (
            <StatusBadge severity="alarm" title="Unavailable">
              Telegram login is temporarily unavailable. Please try again later.
            </StatusBadge>
          )}

          {loading && <SparkLoading description="Verifying Telegram credentials..." />}

          <div
            ref={widgetRef}
            style={{ visibility: loading ? "hidden" : "visible", height: loading ? 0 : "auto" }}
          />

          {botUsername && !widgetReady && !loading && (
            <SparkLoading description="Loading Telegram widget..." />
          )}
        </div>

        {displayError && (
          <StatusBadge severity="alarm" title="Authentication failed" dismissible onDismiss={clearErrors}>
            {displayError}
          </StatusBadge>
        )}

        <div className="form-actions" style={{ marginTop: "1rem", display: "flex", gap: "0.5rem" }}>
          <BracketButton kind="ghost" size="sm" onClick={logout}>
            Clear local session
          </BracketButton>
          <BracketButton
            kind="ghost"
            size="sm"
            href="https://core.telegram.org/widgets/login"
            as="a"
            target="_blank"
            rel="noreferrer"
          >
            About Telegram Login
          </BracketButton>
        </div>

        <hr className="login-divider" style={{ margin: "1rem 0", border: "none", borderTop: "1px solid color-mix(in oklch, var(--frost-ink) 25%, transparent)" }} />

        <Accordion>
          <AccordionItem title="Developer Access">
            <SecretLoginForm />
          </AccordionItem>
        </Accordion>
      </BrutalistCard>
    </div>
  );
}
