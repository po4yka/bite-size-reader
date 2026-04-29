import {
  forwardRef,
  type AnchorHTMLAttributes,
  type ButtonHTMLAttributes,
  type HTMLAttributes,
  type ReactNode,
} from "react";

export interface HeaderProps extends HTMLAttributes<HTMLElement> {
  "aria-label"?: string;
  children?: ReactNode;
}

export function Header({ className, children, ...rest }: HeaderProps) {
  return (
    <header
      className={["rtk-header", className].filter(Boolean).join(" ")}
      {...rest}
    >
      {children}
    </header>
  );
}

export interface HeaderNameProps
  extends Omit<AnchorHTMLAttributes<HTMLAnchorElement>, "prefix"> {
  prefix?: ReactNode;
  children?: ReactNode;
}

export function HeaderName({ prefix, className, children, ...rest }: HeaderNameProps) {
  return (
    <a
      className={["rtk-header__name", className].filter(Boolean).join(" ")}
      {...rest}
    >
      {prefix ? <span className="rtk-header__prefix">{prefix}</span> : null}
      <span className="rtk-header__title">{children}</span>
    </a>
  );
}

export interface HeaderMenuButtonProps
  extends ButtonHTMLAttributes<HTMLButtonElement> {
  "aria-label": string;
  isActive?: boolean;
  isCollapsible?: boolean;
}

export const HeaderMenuButton = forwardRef<HTMLButtonElement, HeaderMenuButtonProps>(
  function HeaderMenuButton(
    { isActive = false, isCollapsible: _isCollapsible, className, ...rest },
    ref,
  ) {
    void _isCollapsible;
    return (
      <button
        ref={ref}
        type="button"
        aria-pressed={isActive}
        className={[
          "rtk-header__menu-button",
          isActive ? "rtk-header__menu-button--active" : null,
          className,
        ]
          .filter(Boolean)
          .join(" ")}
        {...rest}
      >
        <span aria-hidden>≡</span>
      </button>
    );
  },
);

export interface HeaderGlobalBarProps extends HTMLAttributes<HTMLDivElement> {
  children?: ReactNode;
}

export function HeaderGlobalBar({
  className,
  children,
  ...rest
}: HeaderGlobalBarProps) {
  return (
    <div
      className={["rtk-header__global-bar", className].filter(Boolean).join(" ")}
      {...rest}
    >
      {children}
    </div>
  );
}

export interface HeaderGlobalActionProps
  extends ButtonHTMLAttributes<HTMLButtonElement> {
  "aria-label": string;
  isActive?: boolean;
  tooltipAlignment?: "start" | "center" | "end";
  children?: ReactNode;
}

export const HeaderGlobalAction = forwardRef<HTMLButtonElement, HeaderGlobalActionProps>(
  function HeaderGlobalAction(
    { isActive = false, tooltipAlignment: _tt, className, children, ...rest },
    ref,
  ) {
    void _tt;
    return (
      <button
        ref={ref}
        type="button"
        aria-pressed={isActive}
        className={[
          "rtk-header__global-action",
          isActive ? "rtk-header__global-action--active" : null,
          className,
        ]
          .filter(Boolean)
          .join(" ")}
        {...rest}
      >
        {children}
      </button>
    );
  },
);

export interface SkipToContentProps extends AnchorHTMLAttributes<HTMLAnchorElement> {
  href?: string;
  children?: ReactNode;
}

export function SkipToContent({
  href = "#main-content",
  className,
  children = "Skip to main content",
  ...rest
}: SkipToContentProps) {
  return (
    <a
      href={href}
      className={["rtk-skip-to-content", className].filter(Boolean).join(" ")}
      {...rest}
    >
      {children}
    </a>
  );
}
