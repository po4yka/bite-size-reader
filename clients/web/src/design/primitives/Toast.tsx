import {
  type CSSProperties,
  type ReactNode,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";

export type ToastSeverity = "info" | "warn" | "alarm";
export type ToastPosition = "top-right" | "bottom-right" | "bottom-center";

export interface ToastProps {
  title?: ReactNode;
  body?: ReactNode;
  severity?: ToastSeverity;
  position?: ToastPosition;
  durationMs?: number;
  persistent?: boolean;
  onDismiss?: () => void;
  className?: string;
  style?: CSSProperties;
}

const positionStyles: Record<ToastPosition, CSSProperties> = {
  "top-right": { top: "24px", right: "24px", bottom: "auto", left: "auto" },
  "bottom-right": { bottom: "24px", right: "24px", top: "auto", left: "auto" },
  "bottom-center": {
    bottom: "24px",
    left: "50%",
    transform: "translateX(-50%)",
    top: "auto",
    right: "auto",
  },
};

const toastCss = `
  @keyframes frost-toast {
    from { opacity: 0; }
    to   { opacity: 1; }
  }
  .frost-toast {
    animation: frost-toast 0.12s linear forwards;
  }
  .frost-toast--out {
    animation: frost-toast 0.12s linear reverse forwards;
  }
  @media (prefers-reduced-motion: reduce) {
    .frost-toast,
    .frost-toast--out {
      animation: none !important;
      opacity: 1;
    }
  }
`;

const baseToastStyle: CSSProperties = {
  position: "fixed",
  zIndex: 9000,
  minWidth: "240px",
  maxWidth: "400px",
  border: "1px solid var(--frost-ink)",
  borderRadius: "0",
  background: "var(--frost-page)",
  color: "var(--frost-ink)",
  fontFamily: "var(--frost-font-mono)",
  boxSizing: "border-box",
};

const headerStyle: CSSProperties = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  gap: "8px",
  padding: "8px 12px",
  borderBottom: "1px solid color-mix(in oklch, var(--frost-ink) 25%, transparent)",
};

const titleStyle: CSSProperties = {
  fontSize: "var(--frost-type-mono-xs-size)",
  fontWeight: 800,
  letterSpacing: "var(--frost-type-mono-xs-tracking)",
  lineHeight: "var(--frost-type-mono-xs-line-height)",
  textTransform: "uppercase",
  flex: 1,
};

const bodyStyle: CSSProperties = {
  padding: "8px 12px",
  fontSize: "13px",
  fontWeight: 500,
  letterSpacing: "0.4px",
  lineHeight: "1.3",
};

const dismissBtnStyle: CSSProperties = {
  background: "transparent",
  border: "none",
  borderRadius: "0",
  color: "var(--frost-ink)",
  fontFamily: "var(--frost-font-mono)",
  fontSize: "var(--frost-type-mono-xs-size)",
  cursor: "pointer",
  padding: "0 2px",
  lineHeight: 1,
  flexShrink: 0,
};

function glyphForSeverity(severity: ToastSeverity): string | null {
  if (severity === "warn") return "! ";
  return null;
}

export function Toast({
  title,
  body,
  severity = "info",
  position = "bottom-right",
  durationMs = 4000,
  persistent = false,
  onDismiss,
  className,
  style,
}: ToastProps) {
  const [visible, setVisible] = useState(true);
  const [exiting, setExiting] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const dismiss = useCallback(() => {
    setExiting(true);
    timerRef.current = setTimeout(() => {
      setVisible(false);
      onDismiss?.();
    }, 120);
  }, [onDismiss]);

  useEffect(() => {
    if (!persistent && durationMs > 0) {
      timerRef.current = setTimeout(dismiss, durationMs);
    }
    return () => {
      if (timerRef.current != null) clearTimeout(timerRef.current);
    };
  }, [persistent, durationMs, dismiss]);

  if (!visible) return null;

  const isAlarm = severity === "alarm";
  const glyph = glyphForSeverity(severity);

  const computedStyle: CSSProperties = {
    ...baseToastStyle,
    ...positionStyles[position],
    ...(isAlarm
      ? { borderLeft: "var(--frost-spark-web) solid var(--frost-spark)" }
      : {}),
    ...style,
  };

  const cls = [
    "frost-toast",
    exiting ? "frost-toast--out" : null,
    className,
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <>
      <style>{toastCss}</style>
      <div
        role={isAlarm ? "alert" : "status"}
        aria-live={isAlarm ? "assertive" : "polite"}
        className={cls}
        style={computedStyle}
      >
        <div style={headerStyle}>
          <span style={titleStyle}>
            {glyph}
            {title}
          </span>
          <button
            type="button"
            aria-label="Dismiss"
            style={dismissBtnStyle}
            onClick={dismiss}
          >
            ×
          </button>
        </div>
        {body != null ? <div style={bodyStyle}>{body}</div> : null}
      </div>
    </>
  );
}
