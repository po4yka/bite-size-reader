import {
  forwardRef,
  type ButtonHTMLAttributes,
  type ComponentType,
  type ElementType,
  type ReactNode,
} from "react";

export type ButtonKind =
  | "primary"
  | "secondary"
  | "tertiary"
  | "ghost"
  | "danger"
  | "danger--primary"
  | "danger--ghost"
  | "danger--tertiary";

export type ButtonSize = "sm" | "md" | "lg" | "xl";

type RenderIconComp = ComponentType<{ size?: number; "aria-hidden"?: boolean }>;

export interface ButtonProps
  extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "type"> {
  kind?: ButtonKind;
  size?: ButtonSize;
  hasIconOnly?: boolean;
  iconDescription?: string;
  renderIcon?: RenderIconComp;
  isExpressive?: boolean;
  type?: "button" | "submit" | "reset";
  children?: ReactNode;
  /** Optional element/component override. */
  as?: ElementType;
  /** Pass-through href when rendering as an anchor. */
  href?: string;
  target?: string;
  rel?: string;
  /** Pass-through `to` for react-router Link integrations via `as`. */
  to?: string;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  function Button(
    {
      kind = "primary",
      size = "md",
      hasIconOnly = false,
      iconDescription,
      renderIcon: RenderIcon,
      isExpressive: _isExpressive,
      type = "button",
      className,
      children,
      as,
      href,
      ...rest
    },
    ref,
  ) {
    void _isExpressive;
    const classes = [
      "rtk-button",
      `rtk-button--${kind}`,
      `rtk-button--${size}`,
      hasIconOnly ? "rtk-button--icon-only" : null,
      className,
    ]
      .filter(Boolean)
      .join(" ");

    const renderAsElement = as != null || (href != null && as == null);
    const ariaLabel = hasIconOnly ? iconDescription : (rest as { "aria-label"?: string })["aria-label"];
    const titleAttr = hasIconOnly ? iconDescription : (rest as { title?: string }).title;
    const iconNode = RenderIcon ? <RenderIcon size={16} aria-hidden /> : null;
    const innerChildren = hasIconOnly ? null : children;

    if (renderAsElement) {
      const Element: ElementType = as ?? "a";
      return (
        <Element
          ref={ref}
          className={classes}
          aria-label={ariaLabel}
          title={titleAttr}
          {...rest}
          {...(href != null ? { href } : null)}
        >
          {iconNode}
          {innerChildren}
        </Element>
      );
    }

    return (
      <button
        ref={ref}
        type={type}
        className={classes}
        aria-label={ariaLabel}
        title={titleAttr}
        {...rest}
      >
        {iconNode}
        {innerChildren}
      </button>
    );
  },
);
