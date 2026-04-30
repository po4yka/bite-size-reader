/**
 * Back-compat shim: maps the legacy Carbon InlineNotification API
 * (kind/subtitle/hideCloseButton/onClose) to the Frost StatusBadge API
 * (severity/subtitle/dismissible/onDismiss).
 *
 * Used during Phase 4b sweep while call sites are migrated incrementally.
 * Remove once all InlineNotification usages are replaced with StatusBadge.
 */
import { StatusBadge } from "./StatusBadge";
import type { StatusBadgeSeverity } from "./StatusBadge";
import type { ReactNode } from "react";

type LegacyKind = "error" | "warning" | "success" | "info";

function kindToSeverity(kind: LegacyKind | undefined): StatusBadgeSeverity {
  switch (kind) {
    case "error":
      return "alarm";
    case "warning":
      return "warn";
    case "success":
      return "info";
    default:
      return "info";
  }
}

export interface InlineNotificationProps {
  kind?: LegacyKind;
  title?: ReactNode;
  subtitle?: ReactNode;
  hideCloseButton?: boolean;
  onClose?: () => void;
  className?: string;
  style?: React.CSSProperties;
}

export function InlineNotification({
  kind,
  title,
  subtitle,
  hideCloseButton,
  onClose,
  className,
  style,
}: InlineNotificationProps) {
  return (
    <StatusBadge
      severity={kindToSeverity(kind)}
      title={title}
      subtitle={subtitle}
      dismissible={!hideCloseButton && !!onClose}
      onDismiss={onClose}
      className={className}
      style={style}
    />
  );
}
