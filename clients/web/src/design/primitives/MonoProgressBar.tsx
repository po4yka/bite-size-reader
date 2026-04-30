import { type CSSProperties, type ReactNode } from "react";

export type MonoProgressBarStatus = "active" | "finished" | "error";

export interface MonoProgressBarProps {
  label?: ReactNode;
  helperText?: ReactNode;
  hideLabel?: boolean;
  value?: number;
  max?: number;
  status?: MonoProgressBarStatus;
  className?: string;
  style?: CSSProperties;
}

const pulseStyle = `
  .frost-mono-progress-bar--indeterminate .frost-mono-progress-bar__fill {
    animation: frost-pulse 2s ease-in-out infinite;
    width: 100% !important;
  }
  @media (prefers-reduced-motion: reduce) {
    .frost-mono-progress-bar--indeterminate .frost-mono-progress-bar__fill {
      animation: none;
      opacity: 1;
    }
  }
`;

const labelBaseStyle: CSSProperties = {
  fontFamily: "var(--frost-font-mono)",
  fontSize: "var(--frost-type-mono-xs-size)",
  fontWeight: 500,
  letterSpacing: "var(--frost-type-mono-xs-tracking)",
  lineHeight: "var(--frost-type-mono-xs-line-height)",
  textTransform: "uppercase",
  color: "var(--frost-ink)",
  marginBottom: "4px",
  display: "flex",
  alignItems: "center",
  gap: "4px",
};

const trackStyle: CSSProperties = {
  width: "100%",
  height: "8px",
  border: "1px solid var(--frost-ink)",
  borderRadius: "0",
  background: "transparent",
  overflow: "hidden",
  position: "relative",
};

const helperBaseStyle: CSSProperties = {
  fontFamily: "var(--frost-font-mono)",
  fontSize: "var(--frost-type-mono-xs-size)",
  fontWeight: 500,
  letterSpacing: "var(--frost-type-mono-xs-tracking)",
  lineHeight: "var(--frost-type-mono-xs-line-height)",
  textTransform: "uppercase",
  opacity: 0.55,
  marginTop: "4px",
  color: "var(--frost-ink)",
};

export function MonoProgressBar({
  label,
  helperText,
  hideLabel = false,
  value,
  max = 100,
  status = "active",
  className,
  style,
}: MonoProgressBarProps) {
  const isIndeterminate = value === undefined || value === null;
  const pct = isIndeterminate
    ? 0
    : Math.max(0, Math.min(100, ((value ?? 0) / max) * 100));

  const isError = status === "error";
  const isFinished = status === "finished";

  const fillStyle: CSSProperties = {
    height: "100%",
    borderRadius: "0",
    width: isIndeterminate ? "100%" : `${pct}%`,
    background: isError ? "var(--frost-spark)" : "var(--frost-ink)",
    transition: "width 0.2s linear",
  };

  const cls = [
    "frost-mono-progress-bar",
    isIndeterminate ? "frost-mono-progress-bar--indeterminate" : null,
    `frost-mono-progress-bar--${status}`,
    className,
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <>
      <style>{pulseStyle}</style>
      <div className={cls} style={{ ...style }}>
        {label != null && !hideLabel ? (
          <div style={labelBaseStyle}>
            {label}
            {isFinished ? <span aria-hidden>✓</span> : null}
          </div>
        ) : null}
        <div
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={max}
          aria-valuenow={isIndeterminate ? undefined : value}
          style={trackStyle}
        >
          <div
            className="frost-mono-progress-bar__fill"
            style={fillStyle}
          />
        </div>
        {helperText != null ? (
          <div style={helperBaseStyle}>{helperText}</div>
        ) : null}
      </div>
    </>
  );
}
