import { forwardRef, type HTMLAttributes, type ReactNode } from "react";

export interface BrutalistCardProps extends HTMLAttributes<HTMLDivElement> {
  state?: "default" | "critical";
  interactive?: boolean;
  children?: ReactNode;
}

export const BrutalistCard = forwardRef<HTMLDivElement, BrutalistCardProps>(
  function BrutalistCard(
    { state = "default", interactive = false, className, style, children, ...rest },
    ref,
  ) {
    const cls = [
      "frost-card",
      state === "critical" ? "frost-card--critical" : null,
      interactive ? "frost-card--interactive" : null,
      className,
    ]
      .filter(Boolean)
      .join(" ");

    return (
      <div
        ref={ref}
        className={cls}
        style={{
          fontFamily: "var(--frost-font-mono)",
          fontSize: "var(--frost-type-mono-body-size)",
          fontWeight: "var(--frost-type-mono-body-weight)" as React.CSSProperties["fontWeight"],
          letterSpacing: "var(--frost-type-mono-body-tracking)",
          lineHeight: "var(--frost-type-mono-body-line-height)",
          color: "var(--frost-ink)",
          backgroundColor: "var(--frost-page)",
          border: "var(--frost-hairline) solid var(--frost-ink)",
          borderRadius: 0,
          boxShadow: "none",
          padding: "var(--frost-pad-page)",
          display: "flex",
          flexDirection: "column",
          gap: "var(--frost-gap-row)",
          ...(state === "critical"
            ? { borderLeft: "var(--frost-spark-web) solid var(--frost-spark)" }
            : {}),
          ...style,
        }}
        {...rest}
      >
        {children}
      </div>
    );
  },
);

/*
 * Interactive hover thickening is handled via the CSS class below.
 * Inject once into the document head if running in a browser context.
 */
if (typeof document !== "undefined") {
  const STYLE_ID = "frost-card-styles";
  if (!document.getElementById(STYLE_ID)) {
    const el = document.createElement("style");
    el.id = STYLE_ID;
    el.textContent = `
.frost-card--interactive:hover {
  border-width: 2px;
}
@media (prefers-reduced-motion: reduce) {
  .frost-card--interactive {
    transition: none;
  }
}
    `.trim();
    document.head.appendChild(el);
  }
}
