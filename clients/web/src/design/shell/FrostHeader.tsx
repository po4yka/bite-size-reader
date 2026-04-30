import {
  forwardRef,
  type AnchorHTMLAttributes,
  type ButtonHTMLAttributes,
  type ElementType,
  type HTMLAttributes,
  type ReactNode,
} from "react";

/* ─── FrostHeader ─────────────────────────────────────────────────── */

export interface FrostHeaderProps extends HTMLAttributes<HTMLElement> {
  "aria-label"?: string;
  children?: ReactNode;
}

export function FrostHeader({ className, children, style, ...rest }: FrostHeaderProps) {
  return (
    <header
      className={className}
      style={{
        height: "56px",
        width: "100%",
        display: "flex",
        alignItems: "center",
        background: "var(--frost-page)",
        borderBottom: "1px solid var(--frost-ink)",
        boxShadow: "none",
        padding: "0 var(--frost-pad-page, 32px)",
        gap: "16px",
        position: "relative",
        zIndex: 100,
        boxSizing: "border-box",
        ...style,
      }}
      {...rest}
    >
      {children}
    </header>
  );
}

/* ─── FrostHeaderName ─────────────────────────────────────────────── */

export type FrostHeaderNameProps = {
  prefix?: ReactNode;
  children?: ReactNode;
  className?: string;
  as?: ElementType;
} & Omit<AnchorHTMLAttributes<HTMLAnchorElement>, "prefix" | "className"> &
  Record<string, unknown>;

export function FrostHeaderName({
  prefix,
  className,
  children,
  as,
  style,
  ...rest
}: FrostHeaderNameProps) {
  const Element: ElementType = as ?? "a";
  return (
    <Element
      className={className}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "6px",
        fontFamily: "var(--frost-font-mono)",
        fontSize: "13px",
        fontWeight: 800,
        textTransform: "uppercase",
        letterSpacing: "2px",
        lineHeight: "130%",
        color: "var(--frost-ink)",
        textDecoration: "none",
        ...style,
      }}
      {...rest}
    >
      {prefix ? (
        <span style={{ opacity: 0.55 }}>{prefix}</span>
      ) : null}
      <span>{children}</span>
    </Element>
  );
}

/* ─── FrostHeaderMenuButton ───────────────────────────────────────── */

export interface FrostHeaderMenuButtonProps
  extends ButtonHTMLAttributes<HTMLButtonElement> {
  "aria-label": string;
  isActive?: boolean;
  isCollapsible?: boolean;
}

export const FrostHeaderMenuButton = forwardRef<
  HTMLButtonElement,
  FrostHeaderMenuButtonProps
>(function FrostHeaderMenuButton(
  { isActive = false, isCollapsible: _isCollapsible, className, style, ...rest },
  ref,
) {
  void _isCollapsible;
  return (
    <button
      ref={ref}
      type="button"
      aria-pressed={isActive}
      className={className}
      style={{
        fontFamily: "var(--frost-font-mono)",
        fontSize: "11px",
        fontWeight: 800,
        textTransform: "uppercase",
        letterSpacing: "1px",
        border: "1px solid var(--frost-ink)",
        borderRadius: 0,
        background: isActive ? "var(--frost-ink)" : "var(--frost-page)",
        color: isActive ? "var(--frost-page)" : "var(--frost-ink)",
        cursor: "pointer",
        padding: "6px 10px",
        lineHeight: 1,
        ...style,
      }}
      {...rest}
    >
      <span aria-hidden>&#8801;</span>
    </button>
  );
});

/* ─── FrostHeaderGlobalBar ────────────────────────────────────────── */

export interface FrostHeaderGlobalBarProps extends HTMLAttributes<HTMLDivElement> {
  children?: ReactNode;
}

export function FrostHeaderGlobalBar({
  className,
  children,
  style,
  ...rest
}: FrostHeaderGlobalBarProps) {
  return (
    <div
      className={className}
      style={{
        display: "flex",
        alignItems: "center",
        gap: "16px",
        marginLeft: "auto",
        ...style,
      }}
      {...rest}
    >
      {children}
    </div>
  );
}

/* ─── FrostHeaderGlobalAction ─────────────────────────────────────── */

export interface FrostHeaderGlobalActionProps
  extends ButtonHTMLAttributes<HTMLButtonElement> {
  "aria-label": string;
  isActive?: boolean;
  tooltipAlignment?: "start" | "center" | "end";
  children?: ReactNode;
}

export const FrostHeaderGlobalAction = forwardRef<
  HTMLButtonElement,
  FrostHeaderGlobalActionProps
>(function FrostHeaderGlobalAction(
  { isActive = false, tooltipAlignment: _tt, className, children, style, ...rest },
  ref,
) {
  void _tt;
  return (
    <button
      ref={ref}
      type="button"
      aria-pressed={isActive}
      className={className}
      style={{
        fontFamily: "var(--frost-font-mono)",
        fontSize: "11px",
        fontWeight: 800,
        textTransform: "uppercase",
        letterSpacing: "1px",
        border: "none",
        background: "transparent",
        color: "var(--frost-ink)",
        opacity: isActive ? 1 : 0.85,
        cursor: "pointer",
        padding: "6px 8px",
        lineHeight: 1,
        ...style,
      }}
      {...rest}
    >
      {children}
    </button>
  );
});

/* ─── FrostSkipToContent ──────────────────────────────────────────── */

export interface FrostSkipToContentProps
  extends AnchorHTMLAttributes<HTMLAnchorElement> {
  href?: string;
  children?: ReactNode;
}

export function FrostSkipToContent({
  href = "#main-content",
  className,
  children = "Skip to main content",
  style,
  ...rest
}: FrostSkipToContentProps) {
  return (
    <a
      href={href}
      className={className}
      style={{
        position: "absolute",
        left: "-9999px",
        top: "auto",
        width: "1px",
        height: "1px",
        overflow: "hidden",
        fontFamily: "var(--frost-font-mono)",
        fontSize: "11px",
        fontWeight: 800,
        textTransform: "uppercase",
        letterSpacing: "1px",
        ...style,
      }}
      {...rest}
    >
      {children}
    </a>
  );
}
