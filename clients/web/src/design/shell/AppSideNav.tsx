import {
  forwardRef,
  type AnchorHTMLAttributes,
  type HTMLAttributes,
  type ReactNode,
} from "react";

export interface SideNavProps extends HTMLAttributes<HTMLElement> {
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

export const SideNav = forwardRef<HTMLElement, SideNavProps>(function SideNav(
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
          className="rtk-side-nav__overlay"
          onClick={onOverlayClick}
          aria-hidden
        />
      ) : null}
      <nav
        ref={ref}
        aria-label={rest["aria-label"]}
        onBlur={onSideNavBlur}
        className={[
          "rtk-side-nav",
          expanded ? "rtk-side-nav--expanded" : "rtk-side-nav--collapsed",
          className,
        ]
          .filter(Boolean)
          .join(" ")}
        {...rest}
      >
        {children}
      </nav>
    </>
  );
});

export interface SideNavItemsProps extends HTMLAttributes<HTMLUListElement> {
  children?: ReactNode;
}

export function SideNavItems({ className, children, ...rest }: SideNavItemsProps) {
  return (
    <ul
      className={["rtk-side-nav__items", className].filter(Boolean).join(" ")}
      {...rest}
    >
      {children}
    </ul>
  );
}

export interface SideNavLinkProps
  extends AnchorHTMLAttributes<HTMLAnchorElement> {
  isActive?: boolean;
  large?: boolean;
  renderIcon?: React.ComponentType<{ size?: number; "aria-hidden"?: boolean }>;
  element?: React.ElementType;
  children?: ReactNode;
}

export function SideNavLink({
  isActive = false,
  large: _large,
  renderIcon: RenderIcon,
  element,
  className,
  children,
  ...rest
}: SideNavLinkProps) {
  void _large;
  const Component = (element ?? "a") as React.ElementType;
  return (
    <li className="rtk-side-nav__link-wrap">
      <Component
        className={[
          "rtk-side-nav__link",
          isActive ? "rtk-side-nav__link--active" : null,
          className,
        ]
          .filter(Boolean)
          .join(" ")}
        aria-current={isActive ? "page" : undefined}
        {...rest}
      >
        {RenderIcon ? (
          <span className="rtk-side-nav__icon">
            <RenderIcon size={20} aria-hidden />
          </span>
        ) : null}
        <span className="rtk-side-nav__text">{children}</span>
      </Component>
    </li>
  );
}

export function SideNavDivider({
  className,
  ...rest
}: HTMLAttributes<HTMLLIElement>) {
  return (
    <li
      role="separator"
      className={["rtk-side-nav__divider", className].filter(Boolean).join(" ")}
      {...rest}
    />
  );
}
