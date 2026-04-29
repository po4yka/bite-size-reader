import type { CSSProperties, ReactNode } from "react";

export type NotificationKind =
  | "error"
  | "info"
  | "info-square"
  | "success"
  | "warning"
  | "warning-alt";

export interface InlineNotificationProps {
  kind?: NotificationKind;
  title?: ReactNode;
  subtitle?: ReactNode;
  caption?: ReactNode;
  hideCloseButton?: boolean;
  lowContrast?: boolean;
  role?: "alert" | "status" | "log";
  onClose?: () => void;
  onCloseButtonClick?: () => void;
  iconDescription?: string;
  statusIconDescription?: string;
  className?: string;
  style?: CSSProperties;
  children?: ReactNode;
}

export function InlineNotification({
  kind = "info",
  title,
  subtitle,
  caption,
  hideCloseButton = false,
  role = "status",
  onClose,
  onCloseButtonClick,
  className,
  style,
  children,
}: InlineNotificationProps) {
  const cls = [
    "rtk-inline-notification",
    `rtk-inline-notification--${kind}`,
    className,
  ]
    .filter(Boolean)
    .join(" ");
  const handleClose = () => {
    onCloseButtonClick?.();
    onClose?.();
  };
  return (
    <div
      role={role}
      aria-live={kind === "error" ? "assertive" : "polite"}
      className={cls}
      style={style}
    >
      <div className="rtk-inline-notification__body">
        {title ? (
          <p className="rtk-inline-notification__title">{title}</p>
        ) : null}
        {subtitle ? (
          <p className="rtk-inline-notification__subtitle">{subtitle}</p>
        ) : null}
        {caption ? (
          <p className="rtk-inline-notification__caption">{caption}</p>
        ) : null}
        {children}
      </div>
      {hideCloseButton ? null : (
        <button
          type="button"
          aria-label="Close notification"
          className="rtk-inline-notification__close"
          onClick={handleClose}
        >
          ×
        </button>
      )}
    </div>
  );
}
