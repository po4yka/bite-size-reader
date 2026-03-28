import { InlineNotification } from "@carbon/react";

export function DigestUnavailableNotice() {
  return (
    <InlineNotification
      kind="warning"
      title="Digest requires Telegram WebApp context"
      subtitle="Digest endpoints require Telegram initData, so this section is available when opened from Telegram Mini App context."
      hideCloseButton
    />
  );
}
