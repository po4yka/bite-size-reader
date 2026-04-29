import { useState } from "react";
import { Button, InlineLoading, InlineNotification, TextInput, Tile } from "../../design";
import type { ResolvedChannel } from "../../api/digest";
import { useResolveChannel } from "../../hooks/useDigest";

export function ChannelResolvePreview({
  onConfirmSubscribe,
  isSubscribing,
}: {
  onConfirmSubscribe: (username: string) => void;
  isSubscribing: boolean;
}) {
  const [input, setInput] = useState("");
  const [resolvedData, setResolvedData] = useState<ResolvedChannel | null>(null);

  const resolveMutation = useResolveChannel();

  const handleResolve = () => {
    const trimmed = input.trim();
    if (!trimmed) return;
    setResolvedData(null);
    resolveMutation.mutate(trimmed, { onSuccess: (data) => setResolvedData(data) });
  };

  const handleConfirm = () => {
    if (!resolvedData) return;
    onConfirmSubscribe(resolvedData.username);
    setInput("");
    setResolvedData(null);
  };

  return (
    <>
      <div className="form-actions">
        <TextInput
          id="digest-subscribe-input"
          labelText="Channel username"
          placeholder="@channel_name or t.me/channel..."
          value={input}
          onChange={(event) => {
            setInput(event.currentTarget.value);
            setResolvedData(null);
          }}
        />
        <Button
          kind="secondary"
          disabled={!input.trim() || resolveMutation.isPending}
          onClick={handleResolve}
        >
          Preview
        </Button>
      </div>

      {resolveMutation.isPending && <InlineLoading description="Resolving channel..." />}

      {resolveMutation.error && (
        <InlineNotification
          kind="error"
          title="Channel resolve failed"
          subtitle={resolveMutation.error instanceof Error ? resolveMutation.error.message : "Unknown error"}
          hideCloseButton
        />
      )}

      {resolvedData && (
        <Tile style={{ marginTop: "0.5rem" }}>
          <h4>@{resolvedData.username}</h4>
          {resolvedData.title && <p><strong>{resolvedData.title}</strong></p>}
          {resolvedData.description && (
            <p className="muted digest-text-sm">
              {resolvedData.description.length > 300
                ? `${resolvedData.description.slice(0, 300)}...`
                : resolvedData.description}
            </p>
          )}
          {resolvedData.memberCount != null && (
            <p className="muted digest-text-xs">
              {resolvedData.memberCount.toLocaleString()} members
            </p>
          )}
          <Button
            kind="primary"
            size="sm"
            disabled={isSubscribing}
            onClick={handleConfirm}
            style={{ marginTop: "0.5rem" }}
          >
            Confirm Subscribe
          </Button>
        </Tile>
      )}
    </>
  );
}
