import {
  forwardRef,
  type AnchorHTMLAttributes,
  type HTMLAttributes,
  type ReactNode,
} from "react";

/* ─── FrostSideNav ────────────────────────────────────────────────── */

export interface FrostSideNavProps extends HTMLAttributes<HTMLElement> {
  "aria-label"?: string;
  expanded?: boolean;
  defaultExpanded?: boolean;
  isFixedNav?: boolean;
  isRail?: boolean;
  isPersistent?: boolean;
  onSideNavBlur?: () => void;
  onOverlayClick?: () => void;
  children?: ReactNode;
}

export const FrostSideNav = forwardRef<HTMLElement, FrostSideNavProps>(
  function FrostSideNav(
    {
      expanded = false,
      defaultExpanded: _defaultExpanded,
      isFixedNav: _isFixedNav,
      isRail: _isRail,
      isPersistent: _isPersistent,
      onSideNavBlur,
      onOverlayClick,
      className,
      children,
      style,
      ...rest
    },
    ref,
  ) {
    void _defaultExpanded;
    void _isFixedNav;
    void _isRail;
    void _isPersistent;
    return (
      <>
        {expanded ? (
          <div
            onClick={onOverlayClick}
            aria-hidden
            style={{
              position: "fixed",
              inset: 0,
              zIndex: 99,
              background: "color-mix(in oklch, var(--frost-page) 60%, transparent)",
            }}
          />
        ) : null}
        <nav
          ref={ref}
          aria-label={(rest as { "aria-label"?: string })["aria-label"]}
          onBlur={onSideNavBlur}
          className={className}
          style={{
            width: "var(--frost-strip-2, 352px)",
            background: "var(--frost-page)",
            borderRight: "1px solid var(--frost-ink)",
            boxShadow: "none",
            display: "flex",
            flexDirection: "column",
            overflowY: "auto",
            flexShrink: 0,
            ...style,
          }}
          {...rest}
        >
          {children}
        </nav>
      </>
    );
  },
);

/* ─── FrostSideNavItems ───────────────────────────────────────────── */

export interface FrostSideNavItemsProps extends HTMLAttributes<HTMLUListElement> {
  children?: ReactNode;
}

export function FrostSideNavItems({
  className,
  children,
  style,
  ...rest
}: FrostSideNavItemsProps) {
  return (
    <ul
      className={className}
      style={{
        listStyle: "none",
        margin: 0,
        padding: 0,
        ...style,
      }}
      {...rest}
    >
      {children}
    </ul>
  );
}

/* ─── FrostSideNavLink ────────────────────────────────────────────── */

export interface FrostSideNavLinkProps
  extends AnchorHTMLAttributes<HTMLAnchorElement> {
  isActive?: boolean;
  large?: boolean;
  renderIcon?: React.ComponentType<{ size?: number; "aria-hidden"?: boolean }>;
  element?: React.ElementType;
  children?: ReactNode;
}

export function FrostSideNavLink({
  isActive = false,
  large: _large,
  renderIcon: _renderIcon,
  element,
  className,
  children,
  style,
  ...rest
}: FrostSideNavLinkProps) {
  void _large;
  void _renderIcon;
  const Component = (element ?? "a") as React.ElementType;
  return (
    <li>
      <Component
        className={className}
        aria-current={isActive ? "page" : undefined}
        style={{
          display: "block",
          fontFamily: "var(--frost-font-mono)",
          fontSize: "11px",
          fontWeight: 500,
          textTransform: "uppercase",
          letterSpacing: "1px",
          lineHeight: "130%",
          padding: "12px 32px",
          color: "var(--frost-ink)",
          opacity: isActive ? 1 : 0.55,
          textDecoration: "none",
          borderLeft: isActive
            ? "2px solid var(--frost-spark)"
            : "2px solid transparent",
          background: "transparent",
          transition: "opacity 0.08s linear, border-left-color 0.08s linear",
          ...style,
        }}
        {...rest}
      >
        {children}
      </Component>
    </li>
  );
}

/* ─── FrostSideNavDivider ─────────────────────────────────────────── */

export function FrostSideNavDivider({
  className,
  style,
  ...rest
}: HTMLAttributes<HTMLLIElement>) {
  return (
    <li
      role="separator"
      className={className}
      style={{
        height: "1px",
        background: "color-mix(in oklch, var(--frost-ink) 50%, transparent)",
        margin: "16px 0",
        listStyle: "none",
        ...style,
      }}
      {...rest}
    />
  );
}
