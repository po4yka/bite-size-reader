import {
  forwardRef,
  type ButtonHTMLAttributes,
  type ComponentType,
  type ElementType,
  type ReactNode,
} from "react";

export type BracketButtonKind =
  | "primary"
  | "secondary"
  | "tertiary"
  | "ghost"
  | "danger"
  | "danger--primary"
  | "danger--ghost"
  | "danger--tertiary";

export type BracketButtonSize = "sm" | "md" | "lg" | "xl";

type RenderIconComp = ComponentType<{ size?: number; "aria-hidden"?: boolean }>;

export interface BracketButtonProps
  extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "type"> {
  kind?: BracketButtonKind;
  size?: BracketButtonSize;
  hasIconOnly?: boolean;
  iconDescription?: string;
  renderIcon?: RenderIconComp;
  isExpressive?: boolean;
  isLoading?: boolean;
  danger?: boolean;
  type?: "button" | "submit" | "reset";
  children?: ReactNode;
  as?: ElementType;
  href?: string;
  target?: string;
  rel?: string;
  to?: string;
}

const sizeStyles: Record<BracketButtonSize, string> = {
  sm: "4px 12px",
  md: "8px 16px",
  lg: "12px 24px",
  xl: "12px 24px",
};

const baseStyle: React.CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  gap: "4px",
  fontFamily: "var(--frost-font-mono)",
  fontSize: "var(--frost-type-mono-emph-size)",
  fontWeight: "var(--frost-type-mono-emph-weight)" as React.CSSProperties["fontWeight"],
  letterSpacing: "var(--frost-type-mono-emph-tracking)",
  lineHeight: "var(--frost-type-mono-emph-line-height)",
  textTransform: "uppercase",
  border: "1px solid var(--frost-ink)",
  borderRadius: "0",
  background: "var(--frost-page)",
  color: "var(--frost-ink)",
  cursor: "pointer",
  textDecoration: "none",
  transition: "background 0.08s linear, color 0.08s linear",
  userSelect: "none",
  whiteSpace: "nowrap",
};

export const BracketButton = forwardRef<HTMLButtonElement, BracketButtonProps>(
  function BracketButton(
    {
      kind: _kind = "primary",
      size = "md",
      hasIconOnly = false,
      iconDescription,
      renderIcon: RenderIcon,
      isExpressive: _isExpressive,
      isLoading = false,
      danger = false,
      type = "button",
      className,
      children,
      as,
      href,
      disabled,
      style,
      ...rest
    },
    ref,
  ) {
    void _kind;
    void _isExpressive;

    const isDisabled = disabled || isLoading;

    const padding = sizeStyles[size] ?? sizeStyles.md;

    const computedStyle: React.CSSProperties = {
      ...baseStyle,
      padding,
      ...(danger
        ? { borderLeft: `var(--frost-spark-web) solid var(--frost-spark)` }
        : {}),
      ...(isDisabled
        ? { opacity: 0.5, cursor: "not-allowed", pointerEvents: "none" }
        : {}),
      ...style,
    };

    const ariaLabel = hasIconOnly ? iconDescription : (rest as { "aria-label"?: string })["aria-label"];
    const titleAttr = hasIconOnly ? iconDescription : (rest as { title?: string }).title;
    const iconNode = RenderIcon ? <RenderIcon size={16} aria-hidden /> : null;

    const label = isLoading ? (
      <span
        style={{
          display: "inline-block",
          animation: "frost-blinker 0.6s steps(2, start) infinite",
        }}
        aria-label="Loading"
      >
        ···
      </span>
    ) : (
      <>
        {iconNode}
        {hasIconOnly ? null : children}
      </>
    );

    const innerContent = (
      <>
        <span aria-hidden="true">[ </span>
        {label}
        <span aria-hidden="true"> ]</span>
      </>
    );

    const handleMouseDown = (e: React.MouseEvent<HTMLButtonElement>) => {
      (e.currentTarget as HTMLButtonElement).style.transform = "translateY(1px)";
      const onMouseUp = () => {
        (e.currentTarget as HTMLButtonElement).style.transform = "";
        window.removeEventListener("mouseup", onMouseUp);
      };
      window.addEventListener("mouseup", onMouseUp);
    };

    const hoverStyle = `
      .frost-bracket-btn:not(:disabled):hover {
        background: var(--frost-ink) !important;
        color: var(--frost-page) !important;
      }
      .frost-bracket-btn:not(:disabled):active {
        transform: translateY(1px);
      }
      @media (prefers-reduced-motion: reduce) {
        .frost-bracket-btn { transition-duration: 0.001s !important; }
      }
    `;

    const renderAsElement = as != null || (href != null && as == null);

    if (renderAsElement) {
      const Element: ElementType = as ?? "a";
      return (
        <>
          <style>{hoverStyle}</style>
          <Element
            ref={ref}
            className={["frost-bracket-btn", className].filter(Boolean).join(" ")}
            aria-label={ariaLabel}
            title={titleAttr}
            style={computedStyle}
            {...rest}
            {...(href != null ? { href } : null)}
          >
            {innerContent}
          </Element>
        </>
      );
    }

    return (
      <>
        <style>{hoverStyle}</style>
        <button
          ref={ref}
          type={type}
          className={["frost-bracket-btn", className].filter(Boolean).join(" ")}
          aria-label={ariaLabel}
          title={titleAttr}
          disabled={isDisabled}
          onMouseDown={handleMouseDown}
          style={computedStyle}
          {...rest}
        >
          {innerContent}
        </button>
      </>
    );
  },
);
