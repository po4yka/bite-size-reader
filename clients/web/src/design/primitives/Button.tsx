import {
  createElement,
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
  /** Optional element/component override (mirrors Carbon's `as` prop). */
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
    const Element: ElementType = renderAsElement ? (as ?? "a") : "button";
    const elementProps: Record<string, unknown> = {
      ref,
      className: classes,
      "aria-label": hasIconOnly ? iconDescription : (rest as { "aria-label"?: string })["aria-label"],
      title: hasIconOnly ? iconDescription : (rest as { title?: string }).title,
      ...rest,
    };
    if (renderAsElement) {
      if (href != null) elementProps.href = href;
    } else {
      elementProps.type = type;
    }

    return createElement(
      Element,
      elementProps,
      RenderIcon ? <RenderIcon size={16} aria-hidden /> : null,
      hasIconOnly ? null : children,
    );
  },
);
