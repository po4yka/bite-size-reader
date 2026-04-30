import { useState } from "react";
import {
  BracketButton,
  BrutalistCard,
  MonoInput,
  MonoSelect,
  MonoSelectItem,
  MonoTextArea,
  NumberInput,
  StatusBadge,
} from "../../design";
import { useSubmitForward } from "../../hooks/useRequests";
import type { ForwardMetadata } from "../../api/requests";

interface Props {
  onRequestCreated: (requestId: string) => void;
}

export function ForwardForm({ onRequestCreated }: Props) {
  const [text, setText] = useState("");
  const [fromChatId, setFromChatId] = useState<number | "">("");
  const [fromMessageId, setFromMessageId] = useState<number | "">("");
  const [chatTitle, setChatTitle] = useState("");
  const [langPreference, setLangPreference] = useState<"auto" | "en" | "ru">("auto");

  const mutation = useSubmitForward();

  function handleSubmit() {
    if (!text.trim()) return;

    const forwardMetadata: ForwardMetadata | undefined =
      fromChatId !== "" && fromMessageId !== ""
        ? {
            fromChatId: Number(fromChatId),
            fromMessageId: Number(fromMessageId),
            fromChatTitle: chatTitle.trim() || undefined,
          }
        : undefined;

    mutation.mutate(
      { contentText: text.trim(), forwardMetadata, langPreference },
      {
        onSuccess: (result) => {
          if (result.kind === "queued") {
            onRequestCreated(result.requestId);
          }
        },
      },
    );
  }

  const errorMessage =
    mutation.error instanceof Error ? mutation.error.message : "Unknown error occurred.";

  return (
    <BrutalistCard>
      <h3>Submit Telegram Forward</h3>

      <div style={{ marginTop: "1rem" }}>
        <MonoTextArea
          id="forward-content"
          labelText="Forwarded content"
          placeholder="Paste the forwarded message text..."
          rows={6}
          value={text}
          onChange={(e) => setText(e.currentTarget.value)}
          disabled={mutation.isPending}
        />
      </div>

      <p style={{ marginTop: "1rem", fontWeight: 600 }}>Forward metadata (optional)</p>

      <div
        style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem", marginTop: "0.5rem" }}
      >
        <NumberInput
          id="forward-chat-id"
          label="From chat ID"
          value={fromChatId === "" ? "" : fromChatId}
          min={0}
          onChange={(_event: unknown, { value }: { value: string | number }) => {
            const n = Number(value);
            setFromChatId(value === "" ? "" : Number.isFinite(n) ? n : "");
          }}
          disabled={mutation.isPending}
          allowEmpty
        />
        <NumberInput
          id="forward-message-id"
          label="From message ID"
          value={fromMessageId === "" ? "" : fromMessageId}
          min={0}
          onChange={(_event: unknown, { value }: { value: string | number }) => {
            const n = Number(value);
            setFromMessageId(value === "" ? "" : Number.isFinite(n) ? n : "");
          }}
          disabled={mutation.isPending}
          allowEmpty
        />
      </div>

      <div style={{ marginTop: "1rem" }}>
        <MonoInput
          id="forward-chat-title"
          labelText="Chat title (optional)"
          value={chatTitle}
          onChange={(e) => setChatTitle(e.currentTarget.value)}
          disabled={mutation.isPending}
        />
      </div>

      <div style={{ marginTop: "1rem" }}>
        <MonoSelect
          id="forward-lang-preference"
          labelText="Language"
          value={langPreference}
          onChange={(e) => setLangPreference(e.currentTarget.value as "auto" | "en" | "ru")}
          disabled={mutation.isPending}
        >
          <MonoSelectItem value="auto" text="Auto-detect" />
          <MonoSelectItem value="en" text="English" />
          <MonoSelectItem value="ru" text="Russian" />
        </MonoSelect>
      </div>

      <div style={{ marginTop: "1rem" }}>
        <BracketButton onClick={handleSubmit} disabled={!text.trim() || mutation.isPending}>
          {mutation.isPending ? "Submitting..." : "Submit Forward"}
        </BracketButton>
      </div>

      {mutation.isError && (
        <div style={{ marginTop: "1rem" }}>
          <StatusBadge severity="alarm" title="Error" subtitle={errorMessage} />
        </div>
      )}
    </BrutalistCard>
  );
}
