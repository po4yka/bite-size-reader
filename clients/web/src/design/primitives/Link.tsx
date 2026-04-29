import { forwardRef, type AnchorHTMLAttributes, type ReactNode } from "react";

export interface LinkProps extends AnchorHTMLAttributes<HTMLAnchorElement> {
  inline?: boolean;
  visited?: boolean;
  size?: "sm" | "md" | "lg";
  disabled?: boolean;
  renderIcon?: React.ComponentType<{ size?: number; "aria-hidden"?: boolean }>;
  children?: ReactNode;
}

export const Link = forwardRef<HTMLAnchorElement, LinkProps>(function Link(
  {
    inline: _inline,
    visited: _visited,
    size: _size,
    disabled = false,
    renderIcon: RenderIcon,
    className,
    children,
    ...rest
  },
  ref,
) {
  void _inline;
  void _visited;
  void _size;
  const cls = [
    "rtk-link",
    disabled ? "rtk-link--disabled" : null,
    className,
  ]
    .filter(Boolean)
    .join(" ");
  return (
    <a
      ref={ref}
      className={cls}
      aria-disabled={disabled || undefined}
      {...rest}
    >
      {children}
      {RenderIcon ? <RenderIcon size={16} aria-hidden /> : null}
    </a>
  );
});
