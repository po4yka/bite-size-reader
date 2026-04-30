import { forwardRef, type AnchorHTMLAttributes, type ReactNode } from "react";

export interface LinkProps extends AnchorHTMLAttributes<HTMLAnchorElement> {
  inline?: boolean;
  visited?: boolean;
  size?: "sm" | "md" | "lg";
  disabled?: boolean;
  renderIcon?: React.ComponentType<{ size?: number; "aria-hidden"?: boolean }>;
  children?: ReactNode;
}

/** Frost Link — mono inherit-size, hairline underline 1px ink @ 0.4.
 * On hover: underline becomes 1px ink @ 1.0. No color shift.
 */
export const Link = forwardRef<HTMLAnchorElement, LinkProps>(function Link(
  {
    inline: _inline,
    visited: _visited,
    size: _size,
    disabled = false,
    renderIcon: RenderIcon,
    className,
    style,
    children,
    ...rest
  },
  ref,
) {
  void _inline;
  void _visited;
  void _size;

  const cls = [
    "frost-link",
    disabled ? "frost-link--disabled" : null,
    className,
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <a
      ref={ref}
      className={cls}
      aria-disabled={disabled || undefined}
      style={{
        fontFamily: "var(--frost-font-mono)",
        fontSize: "inherit",
        fontWeight: "inherit",
        letterSpacing: "inherit",
        color: "var(--frost-ink)",
        textDecoration: "underline",
        textDecorationColor: "color-mix(in oklch, var(--frost-ink) 40%, transparent)",
        textDecorationThickness: "1px",
        textUnderlineOffset: "2px",
        opacity: disabled ? 0.4 : 1,
        cursor: disabled ? "not-allowed" : "pointer",
        pointerEvents: disabled ? "none" : undefined,
        display: "inline-flex",
        alignItems: "center",
        gap: "var(--frost-gap-inline)",
        ...style,
      }}
      {...rest}
    >
      {children}
      {RenderIcon ? <RenderIcon size={16} aria-hidden /> : null}
    </a>
  );
});

/*
 * Hover style: underline goes from alpha 0.4 to 1.0 on hover.
 * Injected once so we don't repeat in every render.
 */
if (typeof document !== "undefined") {
  const STYLE_ID = "frost-link-styles";
  if (!document.getElementById(STYLE_ID)) {
    const el = document.createElement("style");
    el.id = STYLE_ID;
    el.textContent = `
.frost-link:not(.frost-link--disabled):hover {
  text-decoration-color: var(--frost-ink);
}
    `.trim();
    document.head.appendChild(el);
  }
}
