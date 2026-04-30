import { StatusBadge } from "../design";
import { getErrorMessage } from "../lib/error";

interface QueryErrorNotificationProps {
  error: unknown;
  title: string;
  hideCloseButton?: boolean;
}

export function QueryErrorNotification({
  error,
  title,
  hideCloseButton = true,
}: QueryErrorNotificationProps) {
  if (!error) return null;
  return (
    <StatusBadge
      severity="alarm"
      title={title}
      subtitle={getErrorMessage(error)}
      dismissible={!hideCloseButton}
    />
  );
}
