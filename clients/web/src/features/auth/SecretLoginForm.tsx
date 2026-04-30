import { useState } from "react";
import { Button, InlineLoading, InlineNotification, TextInput } from "../../design";
import { useAuth } from "../../auth/AuthProvider";

const WEB_CLIENT_ID = "web-v1";

export default function SecretLoginForm() {
  const { loginWithSecret } = useAuth();
  const [secretKey, setSecretKey] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!secretKey.trim()) {
      setError("Please enter a secret key.");
      return;
    }

    setLoading(true);
    setError(null);

    try {
      await loginWithSecret({ secretKey: secretKey.trim(), clientId: WEB_CLIENT_ID });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Secret login failed.");
      setSecretKey("");
    } finally {
      setLoading(false);
    }
  };

  return (
    <form onSubmit={(e) => void handleSubmit(e)}>
      {error && (
        <InlineNotification
          kind="error"
          title="Login failed"
          subtitle={error}
          hideCloseButton
          onClose={() => setError(null)}
        />
      )}

      <TextInput
        id="secret-key-input"
        type="password"
        labelText="Secret key"
        placeholder="Enter developer secret key"
        value={secretKey}
        onChange={(e) => setSecretKey(e.target.value)}
        disabled={loading}
        autoComplete="off"
      />

      {loading ? (
        <InlineLoading description="Authenticating..." style={{ marginTop: "1rem" }} />
      ) : (
        <Button
          type="submit"
          kind="primary"
          disabled={!secretKey.trim()}
          style={{ marginTop: "1rem", width: "100%" }}
        >
          Login with Secret Key
        </Button>
      )}
    </form>
  );
}
