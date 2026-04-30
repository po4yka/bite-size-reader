import { BracketButton, BrutalistCard, BrutalistSkeletonText, CodeSnippet, StatusBadge } from "../../design";
import { useTelegramLinkStatus, useBeginTelegramLink, useUnlinkTelegram } from "../../hooks/useUser";
import { QueryErrorNotification } from "../../components/QueryErrorNotification";

const BOT_NAME = "YourBotName";
const MUTED = "color-mix(in oklch, var(--frost-ink) 55%, transparent)";

export default function TelegramLinkSection() {
  const statusQuery = useTelegramLinkStatus();
  const beginLink = useBeginTelegramLink();
  const unlink = useUnlinkTelegram();

  const handleBeginLink = () => {
    beginLink.mutate();
  };

  const handleUnlink = () => {
    unlink.mutate();
  };

  return (
    <BrutalistCard>
      <p
        style={{
          fontFamily: "var(--frost-font-mono)",
          fontSize: "11px",
          fontWeight: 800,
          textTransform: "uppercase",
          letterSpacing: "1px",
          color: MUTED,
          marginBottom: "1rem",
        }}
      >
        § Telegram Account
      </p>

      <QueryErrorNotification error={statusQuery.error} title="Failed to load Telegram link status" />
      <QueryErrorNotification error={beginLink.error} title="Failed to start linking" />
      <QueryErrorNotification error={unlink.error} title="Failed to unlink Telegram" />

      {statusQuery.isLoading && !statusQuery.data && (
        <BrutalistSkeletonText paragraph lineCount={3} />
      )}

      {statusQuery.data && !statusQuery.data.linked && !beginLink.data && (
        <div>
          <p style={{ color: MUTED, marginBottom: "1rem" }}>
            No Telegram account linked.
          </p>
          <BracketButton onClick={handleBeginLink} disabled={beginLink.isPending}>
            Link Telegram Account
          </BracketButton>
        </div>
      )}

      {beginLink.data && !statusQuery.data?.linked && (
        <div>
          <StatusBadge severity="info" title="Linking started">
            {`Send this code to @${BOT_NAME} in Telegram to complete linking.`}
          </StatusBadge>
          <p style={{ marginTop: "1rem", marginBottom: "0.5rem" }}>Your linking code:</p>
          <CodeSnippet type="single">{beginLink.data.nonce}</CodeSnippet>
          <div style={{ marginTop: "1rem" }}>
            <BracketButton
              kind="secondary"
              href={`tg://resolve?domain=${BOT_NAME}&start=${beginLink.data.nonce}`}
              as="a"
            >
              Open in Telegram
            </BracketButton>
          </div>
          <p style={{ marginTop: "0.75rem", fontSize: "0.75rem", color: MUTED }}>
            Code expires in {Math.floor(beginLink.data.expiresIn / 60)} minutes.
          </p>
        </div>
      )}

      {statusQuery.data?.linked && (
        <div>
          {statusQuery.data.telegramUsername && (
            <p style={{ marginBottom: "0.5rem" }}>
              Linked as <strong>@{statusQuery.data.telegramUsername}</strong>
            </p>
          )}
          {statusQuery.data.linkedAt && (
            <p style={{ fontSize: "0.75rem", color: MUTED, marginBottom: "1rem" }}>
              Linked on {new Date(statusQuery.data.linkedAt).toLocaleDateString()}
            </p>
          )}
          <BracketButton kind="danger" onClick={handleUnlink} disabled={unlink.isPending}>
            Unlink
          </BracketButton>
          {unlink.isSuccess && (
            <StatusBadge severity="info" title="Unlinked ✓">
              Telegram account has been unlinked.
            </StatusBadge>
          )}
        </div>
      )}
    </BrutalistCard>
  );
}
