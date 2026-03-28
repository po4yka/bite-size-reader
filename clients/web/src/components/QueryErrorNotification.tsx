import { InlineNotification } from "@carbon/react";
import { getErrorMessage } from "../lib/error";

interface QueryErrorNotificationProps {
  error: unknown;
  title: string;
  hideCloseButton?: boolean;
}

export function QueryErrorNotification({ error, title, hideCloseButton = true }: QueryErrorNotificationProps) {
  if (!error) return null;
  return (
    <InlineNotification
      kind="error"
      title={title}
      subtitle={getErrorMessage(error)}
      hideCloseButton={hideCloseButton}
    />
  );
}
