import {
  forwardRef,
  type ButtonHTMLAttributes,
  type ComponentType,
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
    return (
      <button
        ref={ref}
        type={type}
        className={classes}
        aria-label={hasIconOnly ? iconDescription : rest["aria-label"]}
        title={hasIconOnly ? iconDescription : rest.title}
        {...rest}
      >
        {RenderIcon ? <RenderIcon size={16} aria-hidden /> : null}
        {hasIconOnly ? null : children}
      </button>
    );
  },
);
