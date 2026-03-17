import { useCallback, useEffect, useRef, useState } from "react";
import { Button, InlineLoading, InlineNotification } from "@carbon/react";
import { useAuth } from "../../auth/AuthProvider";

const GOOGLE_SDK_URL = "https://accounts.google.com/gsi/client";

declare global {
  interface Window {
    google?: {
      accounts: {
        id: {
          initialize: (config: GoogleIdConfig) => void;
          prompt: (callback?: (notification: PromptMomentNotification) => void) => void;
        };
      };
    };
  }
}

interface GoogleIdConfig {
  client_id: string;
  callback: (response: GoogleCredentialResponse) => void;
  auto_select?: boolean;
  cancel_on_tap_outside?: boolean;
}

interface GoogleCredentialResponse {
  credential: string;
  select_by?: string;
}

interface PromptMomentNotification {
  isNotDisplayed: () => boolean;
  isSkippedMoment: () => boolean;
  getDismissedReason: () => string;
  getNotDisplayedReason: () => string;
}

export default function GoogleSignInButton() {
  const { loginWithGoogle } = useAuth();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const sdkLoaded = useRef(false);

  const clientId = (import.meta.env.VITE_GOOGLE_CLIENT_ID as string | undefined) ?? "";

  useEffect(() => {
    if (sdkLoaded.current) return;

    const existing = document.querySelector(`script[src="${GOOGLE_SDK_URL}"]`);
    if (existing) {
      sdkLoaded.current = true;
      return;
    }

    const script = document.createElement("script");
    script.src = GOOGLE_SDK_URL;
    script.async = true;
    script.onload = () => {
      sdkLoaded.current = true;
    };
    document.head.appendChild(script);
  }, []);

  const handleClick = useCallback(() => {
    if (!window.google?.accounts?.id) {
      setError("Google Sign In SDK not loaded. Please try again.");
      return;
    }

    if (!clientId) {
      setError("Google Sign In is not configured (missing VITE_GOOGLE_CLIENT_ID).");
      return;
    }

    setLoading(true);
    setError(null);

    window.google.accounts.id.initialize({
      client_id: clientId,
      callback: (response: GoogleCredentialResponse) => {
        void (async () => {
          try {
            await loginWithGoogle({
              idToken: response.credential,
              clientId,
            });
          } catch (err) {
            const message = err instanceof Error ? err.message : "Google sign-in failed.";
            setError(message);
          } finally {
            setLoading(false);
          }
        })();
      },
      cancel_on_tap_outside: true,
    });

    window.google.accounts.id.prompt((notification: PromptMomentNotification) => {
      if (notification.isNotDisplayed() || notification.isSkippedMoment()) {
        setError("Google sign-in prompt was dismissed or not displayed. Please try again.");
        setLoading(false);
      }
    });
  }, [clientId, loginWithGoogle]);

  if (loading) {
    return <InlineLoading description="Signing in with Google..." />;
  }

  return (
    <>
      {error && (
        <InlineNotification
          kind="error"
          title="Google sign-in failed"
          subtitle={error}
          hideCloseButton
          onClose={() => setError(null)}
        />
      )}
      <Button kind="secondary" onClick={handleClick} style={{ width: "100%" }}>
        Sign in with Google
      </Button>
    </>
  );
}
