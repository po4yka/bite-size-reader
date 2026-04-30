import { type CSSProperties, type ReactNode, useCallback } from "react";

export type StatusBadgeSeverity = "info" | "warn" | "alarm";

export interface StatusBadgeProps {
  severity?: StatusBadgeSeverity;
  title?: ReactNode;
  subtitle?: ReactNode;
  caption?: ReactNode;
  dismissible?: boolean;
  onDismiss?: () => void;
  role?: "alert" | "status" | "log";
  className?: string;
  style?: CSSProperties;
  children?: ReactNode;
}

const frameStyle: CSSProperties = {
  display: "inline-flex",
  alignItems: "flex-start",
  gap: 0,
  fontFamily: "var(--frost-font-mono)",
  fontSize: "var(--frost-type-mono-xs-size)",
  letterSpacing: "var(--frost-type-mono-xs-tracking)",
  lineHeight: "var(--frost-type-mono-xs-line-height)",
  textTransform: "uppercase",
  borderRadius: "0",
  background: "var(--frost-page)",
  color: "var(--frost-ink)",
  border: "1px solid var(--frost-ink)",
};

const bodyStyle: CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: "2px",
  padding: "4px 8px",
};

const dismissStyle: CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  justifyContent: "center",
  padding: "4px 6px",
  background: "transparent",
  border: "none",
  borderLeft: "1px solid var(--frost-ink)",
  borderRadius: "0",
  color: "var(--frost-ink)",
  fontFamily: "var(--frost-font-mono)",
  fontSize: "var(--frost-type-mono-xs-size)",
  cursor: "pointer",
  lineHeight: 1,
  flexShrink: 0,
  alignSelf: "stretch",
};

function glyphForSeverity(severity: StatusBadgeSeverity): string | null {
  if (severity === "warn") return "! ";
  return null;
}

function fontWeightForSeverity(severity: StatusBadgeSeverity): CSSProperties["fontWeight"] {
  return severity === "info" ? 500 : 800;
}

export function StatusBadge({
  severity = "info",
  title,
  subtitle,
  caption,
  dismissible = false,
  onDismiss,
  role = "status",
  className,
  style,
  children,
}: StatusBadgeProps) {
  const handleDismiss = useCallback(() => {
    onDismiss?.();
  }, [onDismiss]);

  const isAlarm = severity === "alarm";

  const outerStyle: CSSProperties = {
    ...frameStyle,
    ...(isAlarm
      ? { borderLeft: "var(--frost-spark-web) solid var(--frost-spark)" }
      : {}),
    fontWeight: fontWeightForSeverity(severity),
    ...style,
  };

  const glyph = glyphForSeverity(severity);

  return (
    <div
      role={role}
      aria-live={isAlarm ? "assertive" : "polite"}
      className={className}
      style={outerStyle}
    >
      <div style={bodyStyle}>
        {title != null ? (
          <span>
            {glyph}
            {title}
          </span>
        ) : null}
        {subtitle != null ? (
          <span style={{ fontWeight: 500, textTransform: "none" }}>{subtitle}</span>
        ) : null}
        {caption != null ? (
          <span style={{ opacity: 0.6, fontWeight: 500, textTransform: "none" }}>{caption}</span>
        ) : null}
        {children}
      </div>
      {dismissible ? (
        <button
          type="button"
          aria-label="Dismiss"
          style={dismissStyle}
          onClick={handleDismiss}
        >
          ×
        </button>
      ) : null}
    </div>
  );
}
