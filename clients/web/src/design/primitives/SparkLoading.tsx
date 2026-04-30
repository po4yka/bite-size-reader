import { type CSSProperties, type ReactNode } from "react";

export type SparkLoadingStatus = "active" | "inactive" | "finished" | "error";

export interface SparkLoadingProps {
  status?: SparkLoadingStatus;
  description?: ReactNode;
  className?: string;
  style?: CSSProperties;
}

const wrapperStyle: CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  gap: "6px",
  fontFamily: "var(--frost-font-mono)",
  fontSize: "var(--frost-type-mono-xs-size)",
  fontWeight: 500,
  letterSpacing: "var(--frost-type-mono-xs-tracking)",
  lineHeight: "var(--frost-type-mono-xs-line-height)",
  textTransform: "uppercase",
  color: "var(--frost-ink)",
};

const dotBaseStyle: CSSProperties = {
  display: "inline-block",
  fontFamily: "var(--frost-font-mono)",
  fontSize: "var(--frost-type-mono-xs-size)",
  lineHeight: 1,
  flexShrink: 0,
};

const hoverStyle = `
  @keyframes frost-blinker {
    0%, 100% { opacity: 1; }
    50%       { opacity: 0; }
  }
  .frost-spark-loading--active .frost-spark-loading__dot {
    animation: frost-blinker 0.6s steps(2, start) infinite;
  }
  @media (prefers-reduced-motion: reduce) {
    .frost-spark-loading--active .frost-spark-loading__dot {
      animation: none;
    }
  }
`;

function glyphForStatus(status: SparkLoadingStatus): string {
  if (status === "finished") return "✓";
  if (status === "error") return "!";
  return "·";
}

export function SparkLoading({
  status = "active",
  description,
  className,
  style,
}: SparkLoadingProps) {
  const isError = status === "error";
  const isInactive = status === "inactive";

  const outerStyle: CSSProperties = {
    ...wrapperStyle,
    ...(isError ? { borderLeft: "var(--frost-spark-web) solid var(--frost-spark)" } : {}),
    ...(isError ? { paddingLeft: "6px" } : {}),
    ...style,
  };

  const labelStyle: CSSProperties = {
    opacity: isInactive ? 0.55 : 1,
  };

  const cls = [
    "frost-spark-loading",
    `frost-spark-loading--${status}`,
    className,
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <>
      <style>{hoverStyle}</style>
      <div role="status" className={cls} style={outerStyle}>
        <span className="frost-spark-loading__dot" style={dotBaseStyle} aria-hidden>
          {glyphForStatus(status)}
        </span>
        {description != null ? (
          <span style={labelStyle}>{description}</span>
        ) : null}
      </div>
    </>
  );
}
