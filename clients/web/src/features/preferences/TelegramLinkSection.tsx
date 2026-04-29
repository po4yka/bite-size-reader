import { Button, CodeSnippet, InlineNotification, SkeletonText, Tile } from "../../design";
import { useTelegramLinkStatus, useBeginTelegramLink, useUnlinkTelegram } from "../../hooks/useUser";
import { QueryErrorNotification } from "../../components/QueryErrorNotification";

const BOT_NAME = "YourBotName";

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
    <Tile>
      <h3 style={{ marginBottom: "1rem" }}>Telegram Account</h3>

      <QueryErrorNotification error={statusQuery.error} title="Failed to load Telegram link status" />
      <QueryErrorNotification error={beginLink.error} title="Failed to start linking" />
      <QueryErrorNotification error={unlink.error} title="Failed to unlink Telegram" />

      {statusQuery.isLoading && !statusQuery.data && (
        <SkeletonText paragraph lineCount={3} />
      )}

      {statusQuery.data && !statusQuery.data.linked && !beginLink.data && (
        <div>
          <p style={{ color: "var(--rtk-color-text-muted)", marginBottom: "1rem" }}>
            No Telegram account linked.
          </p>
          <Button onClick={handleBeginLink} disabled={beginLink.isPending}>
            Link Telegram Account
          </Button>
        </div>
      )}

      {beginLink.data && !statusQuery.data?.linked && (
        <div>
          <InlineNotification
            kind="info"
            title="Linking started"
            subtitle={`Send this code to @${BOT_NAME} in Telegram to complete linking.`}
            hideCloseButton
            style={{ marginBottom: "1rem" }}
          />
          <p style={{ marginBottom: "0.5rem" }}>Your linking code:</p>
          <CodeSnippet type="single">{beginLink.data.nonce}</CodeSnippet>
          <div style={{ marginTop: "1rem" }}>
            <Button
              kind="tertiary"
              href={`tg://resolve?domain=${BOT_NAME}&start=${beginLink.data.nonce}`}
              as="a"
            >
              Open in Telegram
            </Button>
          </div>
          <p style={{ marginTop: "0.75rem", fontSize: "0.75rem", color: "var(--rtk-color-text-muted)" }}>
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
            <p style={{ fontSize: "0.75rem", color: "var(--rtk-color-text-muted)", marginBottom: "1rem" }}>
              Linked on {new Date(statusQuery.data.linkedAt).toLocaleDateString()}
            </p>
          )}
          <Button kind="danger--ghost" onClick={handleUnlink} disabled={unlink.isPending}>
            Unlink
          </Button>
          {unlink.isSuccess && (
            <InlineNotification
              kind="success"
              title="Unlinked"
              subtitle="Telegram account has been unlinked."
              hideCloseButton
            />
          )}
        </div>
      )}
    </Tile>
  );
}
