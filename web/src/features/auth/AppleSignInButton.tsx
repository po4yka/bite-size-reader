import { useCallback, useEffect, useRef, useState } from "react";
import { Button, InlineLoading, InlineNotification } from "@carbon/react";
import { useAuth } from "../../auth/AuthProvider";

const APPLE_SDK_URL =
  "https://appleid.cdn-apple.com/appleauth/static/jsapi/appleid/1/en_US/appleid.auth.js";

declare global {
  interface Window {
    AppleID?: {
      auth: {
        init: (config: Record<string, unknown>) => void;
        signIn: () => Promise<AppleSignInResponse>;
      };
    };
  }
}

interface AppleSignInResponse {
  authorization: {
    id_token: string;
    code: string;
    state?: string;
  };
  user?: {
    name?: {
      firstName?: string;
      lastName?: string;
    };
    email?: string;
  };
}

export default function AppleSignInButton() {
  const { loginWithApple } = useAuth();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const sdkLoaded = useRef(false);

  const clientId = import.meta.env.VITE_APPLE_SERVICE_ID as string | undefined;

  useEffect(() => {
    if (sdkLoaded.current) return;

    const existing = document.querySelector(`script[src="${APPLE_SDK_URL}"]`);
    if (existing) {
      sdkLoaded.current = true;
      return;
    }

    const script = document.createElement("script");
    script.src = APPLE_SDK_URL;
    script.async = true;
    script.onload = () => {
      sdkLoaded.current = true;
    };
    document.head.appendChild(script);
  }, []);

  const handleClick = useCallback(async () => {
    if (!window.AppleID) {
      setError("Apple Sign In SDK not loaded. Please try again.");
      return;
    }

    const serviceId = clientId ?? "";
    if (!serviceId) {
      setError("Apple Sign In is not configured (missing VITE_APPLE_SERVICE_ID).");
      return;
    }

    setLoading(true);
    setError(null);

    try {
      window.AppleID.auth.init({
        clientId: serviceId,
        scope: "name email",
        redirectURI: window.location.origin,
        usePopup: true,
      });

      const response: AppleSignInResponse = await window.AppleID.auth.signIn();

      await loginWithApple({
        idToken: response.authorization.id_token,
        clientId: serviceId,
        authCode: response.authorization.code,
        givenName: response.user?.name?.firstName,
        familyName: response.user?.name?.lastName,
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : "Apple sign-in failed.";
      setError(message);
    } finally {
      setLoading(false);
    }
  }, [clientId, loginWithApple]);

  if (loading) {
    return <InlineLoading description="Signing in with Apple..." />;
  }

  return (
    <>
      {error && (
        <InlineNotification
          kind="error"
          title="Apple sign-in failed"
          subtitle={error}
          hideCloseButton
          onClose={() => setError(null)}
        />
      )}
      <Button kind="secondary" onClick={() => void handleClick()} style={{ width: "100%" }}>
        Sign in with Apple
      </Button>
    </>
  );
}
